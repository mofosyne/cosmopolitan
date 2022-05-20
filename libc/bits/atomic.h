#ifndef COSMOPOLITAN_LIBC_BITS_ATOMIC_H_
#define COSMOPOLITAN_LIBC_BITS_ATOMIC_H_
#include "libc/atomic.h"
#if !(__ASSEMBLER__ + __LINKER__ + 0)

/**
 * @fileoverview Cosmopolitan C11 Atomics Library
 *
 *   - Forty-two different ways to say MOV.
 *   - Fourteen different ways to say XCHG.
 *   - Twenty different ways to say LOCK CMPXCHG.
 *
 * It's a lower level programming language than assembly!
 *
 * @see libc/atomic.h
 */

#define memory_order         int
#define memory_order_relaxed 0
#define memory_order_consume 1
#define memory_order_acquire 2
#define memory_order_release 3
#define memory_order_acq_rel 4
#define memory_order_seq_cst 5

#define ATOMIC_VAR_INIT(value)   (value)
#define atomic_is_lock_free(obj) ((void)(obj), sizeof(obj) <= sizeof(void *))

#define atomic_flag      atomic_bool
#define ATOMIC_FLAG_INIT ATOMIC_VAR_INIT(0)
#define atomic_flag_test_and_set_explicit(x, order) \
  atomic_exchange_explicit(x, 1, order)
#define atomic_flag_clear_explicit(x, order) atomic_store_explicit(x, 0, order)

#define atomic_compare_exchange_strong(pObject, pExpected, desired) \
  atomic_compare_exchange_strong_explicit(                          \
      pObject, pExpected, desired, memory_order_seq_cst, memory_order_seq_cst)
#define atomic_compare_exchange_weak(pObject, pExpected, desired) \
  atomic_compare_exchange_weak_explicit(                          \
      pObject, pExpected, desired, memory_order_seq_cst, memory_order_seq_cst)
#define atomic_exchange(pObject, desired) \
  atomic_exchange_explicit(pObject, desired, memory_order_seq_cst)
#define atomic_fetch_add(pObject, operand) \
  atomic_fetch_add_explicit(pObject, operand, memory_order_seq_cst)
#define atomic_fetch_and(pObject, operand) \
  atomic_fetch_and_explicit(pObject, operand, memory_order_seq_cst)
#define atomic_fetch_or(pObject, operand) \
  atomic_fetch_or_explicit(pObject, operand, memory_order_seq_cst)
#define atomic_fetch_sub(pObject, operand) \
  atomic_fetch_sub_explicit(pObject, operand, memory_order_seq_cst)
#define atomic_fetch_xor(pObject, operand) \
  atomic_fetch_xor_explicit(pObject, operand, memory_order_seq_cst)
#define atomic_load(pObject) atomic_load_explicit(pObject, memory_order_seq_cst)
#define atomic_store(pObject, desired) \
  atomic_store_explicit(pObject, desired, memory_order_seq_cst)
#define atomic_flag_test_and_set(x) \
  atomic_flag_test_and_set_explicit(x, memory_order_seq_cst)
#define atomic_flag_clear(x) atomic_flag_clear_explicit(x, memory_order_seq_cst)

#if defined(__CLANG_ATOMIC_BOOL_LOCK_FREE)

#define atomic_init(obj, value)    __c11_atomic_init(obj, value)
#define atomic_thread_fence(order) __c11_atomic_thread_fence(order)
#define atomic_signal_fence(order) __c11_atomic_signal_fence(order)
#define atomic_compare_exchange_strong_explicit(object, expected, desired, \
                                                success, failure)          \
  __c11_atomic_compare_exchange_strong(object, expected, desired, success, \
                                       failure)
#define atomic_compare_exchange_weak_explicit(object, expected, desired, \
                                              success, failure)          \
  __c11_atomic_compare_exchange_weak(object, expected, desired, success, \
                                     failure)
#define atomic_exchange_explicit(object, desired, order) \
  __c11_atomic_exchange(object, desired, order)
#define atomic_fetch_add_explicit(object, operand, order) \
  __c11_atomic_fetch_add(object, operand, order)
#define atomic_fetch_and_explicit(object, operand, order) \
  __c11_atomic_fetch_and(object, operand, order)
#define atomic_fetch_or_explicit(object, operand, order) \
  __c11_atomic_fetch_or(object, operand, order)
#define atomic_fetch_sub_explicit(object, operand, order) \
  __c11_atomic_fetch_sub(object, operand, order)
#define atomic_fetch_xor_explicit(object, operand, order) \
  __c11_atomic_fetch_xor(object, operand, order)
#define atomic_load_explicit(object, order) __c11_atomic_load(object, order)
#define atomic_store_explicit(object, desired, order) \
  __c11_atomic_store(object, desired, order)

#elif (__GNUC__ + 0) * 100 + (__GNUC_MINOR__ + 0) >= 407

#define atomic_init(obj, value)    ((void)(*(obj) = (value)))
#define atomic_thread_fence(order) __atomic_thread_fence(order)
#define atomic_signal_fence(order) __atomic_signal_fence(order)
#define atomic_compare_exchange_strong_explicit(pObject, pExpected, desired, \
                                                success, failure)            \
  __atomic_compare_exchange_n(pObject, pExpected, desired, 0, success, failure)
#define atomic_compare_exchange_weak_explicit(pObject, pExpected, desired, \
                                              success, failure)            \
  __atomic_compare_exchange_n(pObject, pExpected, desired, 1, success, failure)
#define atomic_exchange_explicit(pObject, desired, order) \
  __atomic_exchange_n(pObject, desired, order)
#define atomic_fetch_add_explicit(pObject, operand, order) \
  __atomic_fetch_add(pObject, operand, order)
#define atomic_fetch_and_explicit(pObject, operand, order) \
  __atomic_fetch_and(pObject, operand, order)
#define atomic_fetch_or_explicit(pObject, operand, order) \
  __atomic_fetch_or(pObject, operand, order)
#define atomic_fetch_sub_explicit(pObject, operand, order) \
  __atomic_fetch_sub(pObject, operand, order)
#define atomic_fetch_xor_explicit(pObject, operand, order) \
  __atomic_fetch_xor(pObject, operand, order)
#define atomic_load_explicit(pObject, order) __atomic_load_n(pObject, order)
#define atomic_store_explicit(pObject, desired, order) \
  __atomic_store_n(pObject, desired, order)

#else

#define atomic_init(obj, value)    ((void)(*(obj) = (value)))
#define atomic_thread_fence(order) __sync_synchronize()
#define atomic_signal_fence(order) __asm__ volatile("" ::: "memory")
#define __atomic_apply_stride(object, operand) \
  (((__typeof__(__atomic_val(object)))0) + (operand))
#define atomic_compare_exchange_strong_explicit(object, expected, desired, \
                                                success, failure)          \
  __extension__({                                                          \
    __typeof__(expected) __ep = (expected);                                \
    __typeof__(*__ep) __e = *__ep;                                         \
    (void)(success);                                                       \
    (void)(failure);                                                       \
    (_Bool)((*__ep = __sync_val_compare_and_swap(object, __e, desired)) == \
            __e);                                                          \
  })
#define atomic_compare_exchange_weak_explicit(object, expected, desired,      \
                                              success, failure)               \
  atomic_compare_exchange_strong_explicit(object, expected, desired, success, \
                                          failure)
#if __has_builtin(__sync_swap)
#define atomic_exchange_explicit(object, desired, order) \
  ((void)(order), __sync_swap(object, desired))
#else
#define atomic_exchange_explicit(object, desired, order) \
  __extension__({                                        \
    __typeof__(object) __o = (object);                   \
    __typeof__(desired) __d = (desired);                 \
    (void)(order);                                       \
    __sync_synchronize();                                \
    __sync_lock_test_and_set(&__atomic_val(__o), __d);   \
  })
#endif
#define atomic_fetch_add_explicit(object, operand, order) \
  ((void)(order),                                         \
   __sync_fetch_and_add(object, __atomic_apply_stride(object, operand)))
#define atomic_fetch_and_explicit(object, operand, order) \
  ((void)(order), __sync_fetch_and_and(object, operand))
#define atomic_fetch_or_explicit(object, operand, order) \
  ((void)(order), __sync_fetch_and_or(object, operand))
#define atomic_fetch_sub_explicit(object, operand, order) \
  ((void)(order),                                         \
   __sync_fetch_and_sub(object, __atomic_apply_stride(object, operand)))
#define atomic_fetch_xor_explicit(object, operand, order) \
  ((void)(order), __sync_fetch_and_xor(object, operand))
#define atomic_load_explicit(object, order) \
  ((void)(order), __sync_fetch_and_add(object, 0))
#define atomic_store_explicit(object, desired, order) \
  ((void)atomic_exchange_explicit(object, desired, order))

#endif

#endif /* !(__ASSEMBLER__ + __LINKER__ + 0) */
#endif /* COSMOPOLITAN_LIBC_BITS_ATOMIC_H_ */
