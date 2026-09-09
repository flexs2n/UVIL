#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 0 && x <= 1000) {
    assert((x / 3) * 3 + x % 3 == x);
  }
  return 0;
}
