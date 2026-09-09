#include <stdlib.h>
#include <assert.h>

int main(void) {
  int d = __VERIFIER_nondet_int();
  int z = 100 / d;
  if (d != 0) {
    assert(z <= 100);
  }
  return 0;
}
