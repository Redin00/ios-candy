/*
 * Minimal text console on the Pixel 10 (frankel / laguna) framebuffer
 * + persistent ramoops (0x95200000) + ABL bldr_log (0x95600000).
 */
#include "console.h"
#include "font.h"

#define SCALE		2
#define CH_W		(8 * SCALE)
#define CH_H		(16 * SCALE)
#define MARGIN		24
#define LABEL_COLS	9

#define RAMOOPS_SIG	0x43474244U	/* 'DBGC' */
#define RAMOOPS_MAX	0x001f0000U

volatile uint32_t *con_fb = 0;
static volatile uint32_t *con_fb_alt = 0;
static uint32_t con_bg;
static int row;
static uint32_t ramoops_len;

static inline void dc_civac(uintptr_t addr)
{
	uint64_t sctlr;
	__asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
	if (sctlr & 1)
		__asm__ volatile("dc civac, %0" : : "r"(addr) : "memory");
}

static void con_init(void);

static void log_putc(char c)
{
	if (!ramoops_len)
		con_init();
	if (ramoops_len < RAMOOPS_MAX) {
		volatile uint32_t *hdr = (volatile uint32_t *)RAMOOPS_PMSG;
		volatile char *data = (volatile char *)(RAMOOPS_PMSG + 12);
		uint32_t idx = ramoops_len++;
		data[idx] = c;
		hdr[0] = RAMOOPS_SIG;
		hdr[1] = 0;		/* start: oldest data at offset 0 */
		hdr[2] = ramoops_len;	/* size: valid data count */
		dc_civac((uintptr_t)&data[idx]);
		dc_civac(RAMOOPS_PMSG);
	}
	/* Synopsys DW APB UART serial0 (0x0db62000) TX if active */
	volatile uint32_t *lsr = (volatile uint32_t *)(0x0db62000UL + 0x14);
	volatile uint32_t *thr = (volatile uint32_t *)(0x0db62000UL);
	for (int i = 0; i < 1000; i++) {
		if (*lsr & 0x20) {
			*thr = (uint8_t)c;
			break;
		}
	}
	__asm__ volatile("dsb sy" ::: "memory");
}

static void log_str(const char *s)
{
	while (*s)
		log_putc(*s++);
}

static void con_init(void)
{
	/* Framebuffer writes disabled: ABL tears down VeriSilicon DPU before jump */
	con_fb = 0;
	con_fb_alt = 0;

	/* Initialize ramoops offset by checking existing log buffer in PMSG */
	if (!ramoops_len) {
		volatile uint32_t *hdr = (volatile uint32_t *)RAMOOPS_PMSG;
		if (hdr[0] == RAMOOPS_SIG && hdr[2] > 0 && hdr[2] < RAMOOPS_MAX)
			ramoops_len = hdr[2];
		else
			ramoops_len = 0;
	}
}

void con_flush(void)
{
	con_init();
	uint64_t sctlr;
	__asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
	if ((sctlr & 1) && con_fb) {
		for (uintptr_t off = 0; off < (uintptr_t)FB_STRIDE * FB_H; off += 64) {
			dc_civac((uintptr_t)con_fb + off);
			if (con_fb_alt)
				dc_civac((uintptr_t)con_fb_alt + off);
		}
		__asm__ volatile("dsb sy" ::: "memory");
	}
}

void con_clear(uint32_t bg)
{
	con_init();
	con_bg = bg;
	row = 0;
	if (!con_fb)
		return;
	for (int y = 0; y < FB_H; y++) {
		volatile uint32_t *line0 = con_fb + y * (FB_STRIDE / 4);
		volatile uint32_t *line1 = con_fb_alt ? con_fb_alt + y * (FB_STRIDE / 4) : 0;
		for (int x = 0; x < FB_W; x++) {
			line0[x] = bg;
			if (line1)
				line1[x] = bg;
		}
	}
}

static void put_char(int col, char ch, uint32_t fg)
{
	con_init();
	if (!con_fb)
		return;
	if (ch < 0x20 || ch > 0x7e)
		ch = '?';
	const unsigned char *g = font8x16[ch - 0x20];
	int x0 = MARGIN + col * CH_W, y0 = MARGIN + row * CH_H;
	if (x0 + CH_W > FB_W || y0 + CH_H > FB_H)
		return;
	for (int gy = 0; gy < 16; gy++)
		for (int gx = 0; gx < 8; gx++) {
			uint32_t c = (g[gy] & (0x80 >> gx)) ? fg : con_bg;
			for (int sy = 0; sy < SCALE; sy++) {
				int off = (y0 + gy * SCALE + sy) * (FB_STRIDE / 4)
					  + x0 + gx * SCALE;
				volatile uint32_t *p0 = con_fb + off;
				volatile uint32_t *p1 = con_fb_alt + off;
				for (int sx = 0; sx < SCALE; sx++) {
					p0[sx] = c;
					p1[sx] = c;
				}
			}
		}
}

static int put_str(int col, const char *s, uint32_t fg)
{
	while (*s)
		put_char(col++, *s++, fg);
	return col;
}

static void fmt_hex(char *buf, uint64_t v, int digits)
{
	static const char hex[] = "0123456789ABCDEF";
	for (int i = 0; i < digits; i++)
		buf[i] = hex[(v >> (4 * (digits - 1 - i))) & 0xf];
	buf[digits] = 0;
}

void con_skip(void)
{
	log_putc('\n');
	row++;
}

void con_str(const char *label, const char *s)
{
	log_str("[SHIM] ");
	log_str(label);
	log_str(": ");
	log_str(s);
	log_putc('\n');
	put_str(0, label, YELLOW);
	put_str(LABEL_COLS, s, WHITE);
	row++;
}

void con_hex(const char *label, uint64_t v)
{
	char buf[17];
	fmt_hex(buf, v, 16);
	con_str(label, buf);
}

void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb)
{
	char buf[9];
	log_str("[SHIM] ");
	log_str(label);
	log_str(": ");
	log_str(a);
	fmt_hex(buf, va, 8);
	log_str(buf);
	int col = put_str(0, label, YELLOW);
	col = col < LABEL_COLS ? LABEL_COLS : col + 1;
	col = put_str(col, a, YELLOW);
	col = put_str(col, buf, WHITE);
	if (b) {
		log_putc(' ');
		log_str(b);
		fmt_hex(buf, vb, 8);
		log_str(buf);
		col = put_str(col + 1, b, YELLOW);
		put_str(col, buf, WHITE);
	}
	log_putc('\n');
	row++;
}
