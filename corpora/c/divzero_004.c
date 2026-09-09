#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  int d = __VERIFIER_nondet_int();
  int z = x / d;
  if (d != 0) {
    assert(z == x / d);
  }
  return 0;
}
