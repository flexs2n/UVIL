#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 1000) {
    assert(x / 2 < 100);
  }
  return 0;
}
