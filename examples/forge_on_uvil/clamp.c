#include <stdlib.h>
#include <assert.h>

/* Forge-demo subject: a clamp with a real bug (the upper clamp returns 9,
   so value preservation c == x || c == 10 fails for inputs above 10). */
int main(void) {
  int x = __VERIFIER_nondet_int();
  int c = 0;
  if (x > 10) {
    c = 9;
  } else if (x < 0) {
    c = 0;
  } else {
    c = x;
  }
  assert(c == x || c == 10);
  return 0;
}
