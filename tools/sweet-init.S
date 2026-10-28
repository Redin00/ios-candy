/*
 * First userspace program for SWEET bring-up: mockfs serves the RAM disk
 * itself as /sbin/launchd, so this static binary is PID 1. It proves that
 * exec, the user/kernel boundary, devfs and the console all work, then
 * cleanly reboots after verified execution so the console log in persistent
 * RAMOOPS is preserved for retrieval.
 *
 * tools/mkinit.py wraps the assembled __text into a static Mach-O, so this
 * must stay position independent with no relocations and no writable data:
 * every reference is adr (PC-relative), the PID digit lives on the stack.
 *
 * Raw XNU syscalls: number in x16, svc #0x80, carry set on error.
 */
#define SYS_write	4
#define SYS_open	5
#define SYS_getpid	20
#define SYS_reboot	55
#define SYS_select	93
#define O_RDWR		2

	.text
	.globl	_start
	.p2align 2
_start:
	/*
	 * The kernel enters a static binary with sp at argc, aligned only to
	 * what the argument/apple strings happened to need. Using a misaligned
	 * sp as a base register raises an SP alignment fault (SIGBUS) on real
	 * hardware (QEMU does not check), so align it like crt0/dyld do.
	 */
	mov	x9, sp
	and	x9, x9, #~15
	mov	sp, x9

	adr	x0, path
	mov	x1, #O_RDWR
	mov	x2, #0
	mov	x16, #SYS_open
	svc	#0x80
	b.cs	hang			/* no console: nothing to report to */
	mov	x19, x0

	adr	x1, hello
	adr	x2, hello_tail
	sub	x2, x2, x1
	bl	write_console

	mov	x16, #SYS_getpid
	svc	#0x80
	add	w0, w0, #'0'		/* PID 1 expected: one digit */
	sub	sp, sp, #16
	strb	w0, [sp]
	mov	x1, sp
	mov	x2, #1
	bl	write_console
	add	sp, sp, #16

	adr	x1, hello_tail
	adr	x2, alive1
	sub	x2, x2, x1
	bl	write_console

	/* select(0, NULL, NULL, NULL, &2s) as portable sleep */
	mov	x0, #0
	mov	x1, #0
	mov	x2, #0
	mov	x3, #0
	adr	x4, two_sec
	mov	x16, #SYS_select
	svc	#0x80

	adr	x1, alive1
	adr	x2, alive2
	sub	x2, x2, x1
	bl	write_console

	/* select(0, NULL, NULL, NULL, &2s) */
	mov	x0, #0
	mov	x1, #0
	mov	x2, #0
	mov	x3, #0
	adr	x4, two_sec
	mov	x16, #SYS_select
	svc	#0x80

	adr	x1, alive2
	adr	x2, reboottxt
	sub	x2, x2, x1
	bl	write_console

	adr	x1, reboottxt
	adr	x2, reboottxt_end
	sub	x2, x2, x1
	bl	write_console

	/* select(0, NULL, NULL, NULL, &1s) */
	mov	x0, #0
	mov	x1, #0
	mov	x2, #0
	mov	x3, #0
	adr	x4, one_sec
	mov	x16, #SYS_select
	svc	#0x80

	/* Clean PSCI warm reset via SYS_reboot (RB_AUTOBOOT = 0) */
	mov	x0, #0			/* opt = 0 (RB_AUTOBOOT) */
	mov	x1, #0			/* command = NULL */
	mov	x16, #SYS_reboot
	svc	#0x80

hang:
	b	hang

/* write(x19, x1, x2) */
write_console:
	mov	x0, x19
	mov	x16, #SYS_write
	svc	#0x80
	ret

	.p2align 3
two_sec:
	.quad	2			/* tv_sec */
	.quad	0			/* tv_usec */
one_sec:
	.quad	1
	.quad	0
path:
	.asciz	"/dev/console"
hello:
	.ascii	"\n*** SWEET userspace: init running as PID "
hello_tail:
	.ascii	" ***\n"
alive1:
	.ascii	"SWEET init: heartbeat 1 (alive)\n"
alive2:
	.ascii	"SWEET init: heartbeat 2 (alive)\n"
reboottxt:
	.ascii	"SWEET init: userspace milestone 5 verified, executing SYS_reboot...\n"
reboottxt_end:
