#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""計測ASMのTL0読取り窓を検査。48Fsys clock/命令という保守モデルを明示する。"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from functools import lru_cache
from check_stack import parse_assembly


class TimingWindowError(ValueError):
    pass


def analyze(assembly):
    functions=[f for f in parse_assembly(assembly) if f.name=='_timing_poll']
    if len(functions)!=1:raise TimingWindowError('one timing_poll required')
    fn=functions[0];ins=fn.instructions
    def locations(op,operands):
        return [i for i,(actual,args,_) in enumerate(ins)
                if actual==op and [a.lower() for a in args]==operands]
    def one(items):
        if len(items)!=1:raise TimingWindowError('ambiguous timing boundary')
        return items[0]
    masked=one(locations('clr',['_ea']));restored=one(locations('mov',['_ea','c']))
    stopped=one(locations('clr',['_tr2']));started=one(locations('setb',['_tr2']))
    reads=[i for i,(op,args,_) in enumerate(ins)
           if op=='mov' and len(args)==2 and args[1].lower()=='_tl0']
    if len(reads)!=2 or not masked<reads[0]<stopped<started<reads[1]<restored:
        raise TimingWindowError('timing/interrupt boundary order mismatch')
    writes=[i for i,(op,args,_) in enumerate(ins)
            if args and args[0].lower()=='_ea' and op in ('mov','clr','setb')]
    if writes!=[masked,restored]:raise TimingWindowError('unexpected interrupt write')

    def longest(first,last):
        @lru_cache(None)
        def visit(at):
            if not first<=at<=last:raise TimingWindowError('branch escapes timing window')
            op,args,_=ins[at]
            if op not in ('mov','clr','setb','jnb','sjmp','subb'):
                raise TimingWindowError('unqualified instruction in timing window')
            for value in args:
                token=value.lower().replace(' ','').replace('(','').replace(')','')
                if token in ('a','c','_ea','_tr2','_tf2','_tl0','_tl2','_th2'):continue
                if re.fullmatch(r'r[0-7]',token):continue
                if value in fn.labels:continue
                if re.fullmatch(r'_timing_poll_(?:elapsed|enabled)_[\d_]+(?:\+(?:0x0*[01]|[01]))?',token):continue
                if token.startswith('#'):
                    try:
                        if 0<=int(token[1:],0)<=255:continue
                    except ValueError:pass
                raise TimingWindowError('unqualified operand in timing window')
            if at==last:return 1
            successors=[at+1]
            if op in ('jnb','sjmp'):
                target=fn.labels.get(args[-1])
                if target is None or target<=at:raise TimingWindowError('loop/unknown timing target')
                successors=([at+1,target] if op=='jnb' else [target])
            return 1+max(visit(n) for n in successors)
        return visit(first)

    read_count=longest(reads[0],reads[1]);masked_count=longest(masked,restored)


    ticks=read_count*4
    if ticks>=256:raise TimingWindowError('TL0 difference can alias under cycle model')
    return {'read_window_instructions':read_count,'interrupt_mask_instructions':masked_count,
            'instruction_clock_ceiling_model':48,'timer_tick_system_clocks':12,
            'read_window_ticks_model_bound':ticks,'modulus_ticks':256,
            'timer0_delta_nonaliasing_under_model':True,
            'exact_ch552_instruction_cycles_verified':False,'hardware_execution_verified':False}


def qualify(assembly,image,stack_report):
    report=json.loads(Path(stack_report).read_text())
    binary=Path(image).read_bytes()
    if len(binary)!=14336:raise TimingWindowError('application image size mismatch')
    digest=hashlib.sha256(binary).hexdigest()
    asm_digest=hashlib.sha256(Path(assembly).read_bytes()).hexdigest()
    if (report.get('image_padded_sha256')!=digest
            or report.get('assembly_sha256',{}).get(Path(assembly).name)!=asm_digest):
        raise TimingWindowError('stack/image/assembly evidence mismatch')
    return dict(analyze(assembly),image_sha256=digest,assembly_sha256=asm_digest)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembly',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--stack-report',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        result=qualify(args.assembly,args.image,args.stack_report)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    except (ValueError,OSError) as error:parser.exit(1,f'timing窓検査を停止: {error}\n')


if __name__=='__main__':main()
