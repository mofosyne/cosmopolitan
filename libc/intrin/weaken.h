#ifndef COSMOPOLITAN_LIBC_BITS_WEAKEN_H_
#define COSMOPOLITAN_LIBC_BITS_WEAKEN_H_
#if !(__ASSEMBLER__ + __LINKER__ + 0)

#define _weaken(symbol)                                         \
  __extension__({                                               \
    extern __typeof__(symbol) symbol __attribute__((__weak__)); \
    &symbol;                                                    \
  })

#endif /* !(__ASSEMBLER__ + __LINKER__ + 0) */
#endif /* COSMOPOLITAN_LIBC_BITS_WEAKEN_H_ */
