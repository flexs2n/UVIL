#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a = __VERIFIER_nondet_int();
  int s = 7;
  for (int i = 0; i < 30; i++) {
    s = (s * 31 + a) % 1000003;
  }
  assert(s != 42);
  return 0;
}
