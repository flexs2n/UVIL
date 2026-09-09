#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x > 2147483640) {
    assert(x + 7 > x);
  }
  return 0;
}
