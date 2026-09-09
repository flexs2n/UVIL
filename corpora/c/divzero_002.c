#include <stdlib.h>
#include <assert.h>

int main(void) {
  int d = __VERIFIER_nondet_int();
  int z = d / d;
  if (d != 0) {
    assert(z == 1);
  }
  return 0;
}
