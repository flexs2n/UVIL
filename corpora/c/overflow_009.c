#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 3 && x <= 6) {
    assert(x * x != 25);
  }
  return 0;
}
