#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a = __VERIFIER_nondet_int();
  int s = 9;
  for (int i = 0; i < 24; i++) {
    s = (s * 53 + a) % 2147483647;
  }
  assert(s != 100);
  return 0;
}
