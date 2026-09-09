#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a = __VERIFIER_nondet_int();
  int s = 13;
  for (int i = 0; i < 32; i++) {
    s = (s * 29 + a) % 7919;
  }
  assert(s != 5);
  return 0;
}
