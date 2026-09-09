#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a = __VERIFIER_nondet_int();
  int s = 3;
  for (int i = 0; i < 28; i++) {
    s = (s * 37 + a) % 999983;
  }
  assert(s != 7);
  return 0;
}
