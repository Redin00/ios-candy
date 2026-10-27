#pragma once
#include <stdint.h>

#define FB_BASE		0xb0000000UL	/* ABL primary framebuffer on Pixel 10 */
#define FB_ALT_BASE	0xc4a00000UL	/* ABL alternate framebuffer on Pixel 10 */
#define FB_W		1080
#define FB_H		2424
#define FB_STRIDE	(FB_W * 4)	/* a8r8g8b8, 4320 bytes/line */

#define DPU_BASE	0x0ee00000UL	/* VeriSilicon DC9x00 MMIO base */
#define RAMOOPS_CON	0x95200000UL	/* ramoops@95200000 console-ramoops-0 */
#define RAMOOPS_PMSG	0x95400000UL	/* ramoops@95200000 pmsg-ramoops-0 */
#define BLDR_LOG_BASE	0x95600000UL	/* bldr_log_reserved@95600000 */

#define RED	0xffff0000U
#define BLUE	0xff0000a0U
#define WHITE	0xffffffffU
#define YELLOW	0xffffff00U
#define GREEN	0xff00ff00U

extern volatile uint32_t *con_fb;

void con_clear(uint32_t bg);
void con_skip(void);
void con_str(const char *label, const char *s);
void con_hex(const char *label, uint64_t v);
/* label, then "a=xxxxxxxx b=xxxxxxxx" style pairs of 32-bit values */
void con_hex2(const char *label, const char *a, uint32_t va, const char *b, uint32_t vb);
void con_flush(void);
