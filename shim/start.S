/*
 * Pixel 10 (frankel / laguna, Tensor G5) boot shim entry:
 * arm64 Linux Image header so ABL treats us like a kernel.
 * ABL enters at EL2 (or EL1), MMU/D-cache off, x0 = DTB pointer (0x8a000000).
 */
	.section .text.head, "ax"
	.globl _head
_head:
	b	_start			/* code0 */
	.long	0			/* code1 */
	.quad	0x80000			/* text_offset */
	.quad	_end - _head		/* image_size */
	.quad	0xa			/* flags: LE, 4K pages, place anywhere */
	.quad	0			/* res2 */
	.quad	0			/* res3 */
	.quad	0			/* res4 */
	.ascii	"ARM\x64"		/* magic */
	.long	0			/* res5 (PE offset) */

	.text
/*
 * Drop from EL2 to EL1h if CurrentEL == EL2.
 * Preserves x0, x19, x20, x30 (lr). Clobbers x1, x2.
 */
drop_el2_to_el1:
	mrs	x1, CurrentEL
	cmp	x1, #0x8
	b.ne	1f
	/* Enable EL1 access to GICv3 CPU interface (ICC_SRE_EL2) */
	mrs	x2, S3_4_C12_C9_5
	orr	x2, x2, #0x8		/* Enable (bit 3) */
	orr	x2, x2, #0x1		/* SRE (bit 0) */
	msr	S3_4_C12_C9_5, x2
	isb
	msr	S3_4_C12_C11_0, xzr	/* ICH_HCR_EL2 = 0 */
	/* Enable EL1 access to physical/virtual timers */
	mrs	x2, cnthctl_el2
	orr	x2, x2, #0x3		/* EL1PCTEN | EL1PCEN */
	msr	cnthctl_el2, x2
	msr	cntvoff_el2, xzr
	/* HCR_EL2: RW=1 (bit 31), APK=1 (bit 40), API=1 (bit 41) */
	mov	x2, #(1 << 31)
	movk	x2, #0x0300, lsl #32
	msr	hcr_el2, x2
	/* Disable EL2 FP/SIMD traps */
	mov	x2, #0x33ff
	msr	cptr_el2, x2
	/* Mirror MIDR/MPIDR to virtual ID registers */
	mrs	x2, midr_el1
	msr	vpidr_el2, x2
	mrs	x2, mpidr_el1
	msr	vmpidr_el2, x2
	/* Clean SCTLR_EL1 before entering EL1 (MMU/caches off) */
	mov	x2, #0x0800
	movk	x2, #0x30d0, lsl #16
	msr	sctlr_el1, x2
	/* ERET to EL1h with DAIF masked */
	mov	x2, #0x3c5
	msr	spsr_el2, x2
	msr	elr_el2, x30
	isb
	eret
1:	ret

	.globl _start
_start:
	msr	daifset, #0xf
	mov	x19, x0			/* DTB pointer from ABL */
	mrs	x20, CurrentEL		/* Record entry EL before any drop */
	bl	drop_el2_to_el1
	/* Enable FP/SIMD at EL1 (CPACR_EL1.FPEN = 3) */
	mov	x1, #(3 << 20)
	msr	cpacr_el1, x1
	msr	spsel, #1
	adr	x1, _stack_top
	mov	sp, x1
	adr	x1, vectors
	msr	vbar_el1, x1
	isb
	/* zero .bss */
	adr	x1, _bss_start
	adr	x2, _bss_end
1:	cmp	x1, x2
	b.hs	2f
	str	xzr, [x1], #8
	b	1b
2:	mov	x0, x19
	mov	x1, x20			/* Pass entry EL to shim_main */
	bl	shim_main
3:	wfe
	b	3b

/* PSCI CPU_ON target. x0 = context id = cpu index (1..7). */
	.globl secondary_entry
secondary_entry:
	msr	daifset, #0xf
	mov	x19, x0
	bl	drop_el2_to_el1
	mov	x1, #(3 << 20)
	msr	cpacr_el1, x1
	msr	spsel, #1
	mov	x0, x19
	adr	x1, _sec_stacks
	add	x1, x1, x0, lsl #12
	add	x1, x1, #0x1000
	mov	sp, x1
	adr	x1, vectors
	msr	vbar_el1, x1
	isb
	bl	secondary_main
4:	wfe
	b	4b

/*
 * Exception vectors. Each slot stashes x29/x30, loads its slot number
 * and jumps to the common path, which saves x0-x28 and calls
 * exc_handler(slot, regs). IRQs return; everything else ends in the
 * on-screen panic.
 */
.macro vent slot
	.balign	0x80
	stp	x29, x30, [sp, #-16]!
	mov	x29, #\slot
	b	exc_common
.endm

	.balign	0x800
	.globl vectors
vectors:
	vent 0
	vent 1
	vent 2
	vent 3
	vent 4
	vent 5
	vent 6
	vent 7
	vent 8
	vent 9
	vent 10
	vent 11
	vent 12
	vent 13
	vent 14
	vent 15

exc_common:
	sub	sp, sp, #(30 * 8)
	stp	x0, x1, [sp, #0]
	stp	x2, x3, [sp, #16]
	stp	x4, x5, [sp, #32]
	stp	x6, x7, [sp, #48]
	stp	x8, x9, [sp, #64]
	stp	x10, x11, [sp, #80]
	stp	x12, x13, [sp, #96]
	stp	x14, x15, [sp, #112]
	stp	x16, x17, [sp, #128]
	stp	x18, x19, [sp, #144]
	stp	x20, x21, [sp, #160]
	stp	x22, x23, [sp, #176]
	stp	x24, x25, [sp, #192]
	stp	x26, x27, [sp, #208]
	str	x28, [sp, #224]
	mov	x0, x29
	mov	x1, sp
	bl	exc_handler
	ldp	x0, x1, [sp, #0]
	ldp	x2, x3, [sp, #16]
	ldp	x4, x5, [sp, #32]
	ldp	x6, x7, [sp, #48]
	ldp	x8, x9, [sp, #64]
	ldp	x10, x11, [sp, #80]
	ldp	x12, x13, [sp, #96]
	ldp	x14, x15, [sp, #112]
	ldp	x16, x17, [sp, #128]
	ldp	x18, x19, [sp, #144]
	ldp	x20, x21, [sp, #160]
	ldp	x22, x23, [sp, #176]
	ldp	x24, x25, [sp, #192]
	ldp	x26, x27, [sp, #208]
	ldr	x28, [sp, #224]
	add	sp, sp, #(30 * 8)
	ldp	x29, x30, [sp], #16
	eret
