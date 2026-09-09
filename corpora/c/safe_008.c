#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= -50 && x <= 50) {
    assert(x <= 50);
  }
  return 0;
}
