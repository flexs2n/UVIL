#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 0 && x < 100) {
    assert(x < 100);
  }
  return 0;
}
