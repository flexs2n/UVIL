#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 0 && x % 2 == 0) {
    assert((x / 2) * 2 == x);
  }
  return 0;
}
