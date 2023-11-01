/*-*- mode:c;indent-tabs-mode:nil;c-basic-offset:2;tab-width:8;coding:utf-8 -*-│
│vi: set net ft=c ts=2 sts=2 sw=2 fenc=utf-8                                :vi│
╞══════════════════════════════════════════════════════════════════════════════╡
│ Copyright 2022 Justine Alexandra Roberts Tunney                              │
│                                                                              │
│ Permission to use, copy, modify, and/or distribute this software for         │
│ any purpose with or without fee is hereby granted, provided that the         │
│ above copyright notice and this permission notice appear in all copies.      │
│                                                                              │
│ THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL                │
│ WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED                │
│ WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE             │
│ AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL         │
│ DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR        │
│ PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER               │
│ TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR             │
│ PERFORMANCE OF THIS SOFTWARE.                                                │
╚─────────────────────────────────────────────────────────────────────────────*/
#include "libc/intrin/cxaatexit.internal.h"
#include "libc/runtime/runtime.h"
#include "libc/testlib/subprocess.h"
#include "libc/testlib/testlib.h"
#include "libc/thread/thread.h"

#define MAIN  150
#define CHILD 170

pthread_t main_thread;
_Thread_local static int exit_code;

void OnExit(void) {
  _Exit(exit_code);
}

void *Worker(void *arg) {
  ASSERT_EQ(0, pthread_join(main_thread, 0));
  exit_code = CHILD;
  pthread_exit(0);
}

TEST(pthread_exit, joinableOrphanedChild_runsAtexitHandlers) {
  pthread_t th;
  pthread_attr_t attr;
  SPAWN(fork);
  atexit(OnExit);
  exit_code = MAIN;
  main_thread = pthread_self();
  ASSERT_EQ(0, pthread_attr_init(&attr));
  ASSERT_EQ(0, pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_JOINABLE));
  ASSERT_EQ(0, pthread_create(&th, &attr, Worker, 0));
  ASSERT_EQ(0, pthread_attr_destroy(&attr));
  pthread_exit(0);
  EXITS(CHILD);
}

TEST(pthread_exit, detachedOrphanedChild_runsAtexitHandlers) {
  pthread_t th;
  pthread_attr_t attr;
  SPAWN(fork);
  atexit(OnExit);
  exit_code = MAIN;
  main_thread = pthread_self();
  ASSERT_EQ(0, pthread_attr_init(&attr));
  ASSERT_EQ(0, pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED));
  ASSERT_EQ(0, pthread_create(&th, &attr, Worker, 0));
  ASSERT_EQ(0, pthread_attr_destroy(&attr));
  pthread_exit(0);
  EXITS(CHILD);
}

void OnMainThreadExit(void *arg) {
  _Exit((long)arg);
}

TEST(__cxa_thread_atexit, exit_wontInvokeThreadDestructors) {
  SPAWN(fork);
  __cxa_thread_atexit(OnMainThreadExit, (void *)123L, 0);
  exit(0);
  EXITS(0);
}

TEST(__cxa_thread_atexit, pthread_exit_willInvokeThreadDestructors) {
  SPAWN(fork);
  __cxa_thread_atexit(OnMainThreadExit, (void *)123L, 0);
  pthread_exit(0);
  EXITS(123);
}
