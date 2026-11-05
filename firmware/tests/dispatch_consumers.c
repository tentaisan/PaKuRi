/* SPDX-License-Identifier: Apache-2.0 */
#include "../experimental/standalone/dispatch.h"
MgDispatchSnapshot dispatch_seen_1, dispatch_seen_2;
unsigned dispatch_calls_1, dispatch_calls_2;
void dispatch_probe_1(const MgDispatchSnapshot *s) { dispatch_seen_1=*s; ++dispatch_calls_1; }
void dispatch_probe_2(const MgDispatchSnapshot *s) { dispatch_seen_2=*s; ++dispatch_calls_2; }
