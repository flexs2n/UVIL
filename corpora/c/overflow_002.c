#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x > 46340) {
    assert(x * x > 0);
  }
  return 0;
}
