#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 0) {
    assert(x - x == 0);
  }
  return 0;
}
