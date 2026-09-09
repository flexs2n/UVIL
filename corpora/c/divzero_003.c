#include <stdlib.h>
#include <assert.h>

int main(void) {
  int d = __VERIFIER_nondet_int();
  int z = 42 % d;
  if (d != 0) {
    assert(z < 42);
  }
  return 0;
}
