#-*-mode:makefile-gmake;indent-tabs-mode:t;tab-width:8;coding:utf-8-*-┐
#── vi: set noet ft=make ts=8 sw=8 fenc=utf-8 :vi ────────────────────┘

PKGS += THIRD_PARTY_HIREDIS

THIRD_PARTY_HIREDIS_ARTIFACTS += THIRD_PARTY_HIREDIS_A
THIRD_PARTY_HIREDIS = $(THIRD_PARTY_HIREDIS_A_DEPS) $(THIRD_PARTY_HIREDIS_A)
THIRD_PARTY_HIREDIS_A = o/$(MODE)/third_party/hiredis/hiredis.a
THIRD_PARTY_HIREDIS_A_FILES := $(wildcard third_party/hiredis/*)
THIRD_PARTY_HIREDIS_A_HDRS = $(filter %.h,$(THIRD_PARTY_HIREDIS_A_FILES))
THIRD_PARTY_HIREDIS_A_INCS = $(filter %.inc,$(THIRD_PARTY_HIREDIS_A_FILES))
THIRD_PARTY_HIREDIS_A_SRCS = $(filter %.c,$(THIRD_PARTY_HIREDIS_A_FILES))

THIRD_PARTY_HIREDIS_A_OBJS =				\
	$(THIRD_PARTY_HIREDIS_A_SRCS:%.c=o/$(MODE)/%.o)

THIRD_PARTY_HIREDIS_A_DIRECTDEPS =			\
	LIBC_CALLS					\
	LIBC_DNS					\
	LIBC_FMT					\
	LIBC_INTRIN					\
	LIBC_MEM					\
	LIBC_NEXGEN32E					\
	LIBC_RUNTIME					\
	LIBC_SOCK					\
	LIBC_STDIO					\
	LIBC_STR					\
	LIBC_SYSV					\
	LIBC_TIME					\
	LIBC_X						\
	THIRD_PARTY_GDTOA

THIRD_PARTY_HIREDIS_A_DEPS :=				\
	$(call uniq,$(foreach x,$(THIRD_PARTY_HIREDIS_A_DIRECTDEPS),$($(x))))

THIRD_PARTY_HIREDIS_A_CHECKS =				\
	$(THIRD_PARTY_HIREDIS_A).pkg			\
	$(THIRD_PARTY_HIREDIS_A_HDRS:%=o/$(MODE)/%.ok)

$(THIRD_PARTY_HIREDIS_A):				\
		third_party/hiredis/			\
		$(THIRD_PARTY_HIREDIS_A).pkg		\
		$(THIRD_PARTY_HIREDIS_A_OBJS)

$(THIRD_PARTY_HIREDIS_A).pkg:				\
		$(THIRD_PARTY_HIREDIS_A_OBJS)		\
		$(foreach x,$(THIRD_PARTY_HIREDIS_A_DIRECTDEPS),$($(x)_A).pkg)

THIRD_PARTY_HIREDIS_LIBS = $(foreach x,$(THIRD_PARTY_HIREDIS_ARTIFACTS),$($(x)))
THIRD_PARTY_HIREDIS_HDRS = $(foreach x,$(THIRD_PARTY_HIREDIS_ARTIFACTS),$($(x)_HDRS))
THIRD_PARTY_HIREDIS_SRCS = $(foreach x,$(THIRD_PARTY_HIREDIS_ARTIFACTS),$($(x)_SRCS))
THIRD_PARTY_HIREDIS_INCS = $(foreach x,$(THIRD_PARTY_HIREDIS_ARTIFACTS),$($(x)_INCS))
THIRD_PARTY_HIREDIS_CHECKS = $(foreach x,$(THIRD_PARTY_HIREDIS_ARTIFACTS),$($(x)_CHECKS))
THIRD_PARTY_HIREDIS_OBJS = $(foreach x,$(THIRD_PARTY_HIREDIS_ARTIFACTS),$($(x)_OBJS))

$(THIRD_PARTY_HIREDIS_OBJS): third_party/hiredis/BUILD.mk

.PHONY: o/$(MODE)/third_party/hiredis
o/$(MODE)/third_party/hiredis: $(THIRD_PARTY_HIREDIS_CHECKS)
