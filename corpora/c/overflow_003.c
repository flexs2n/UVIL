#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x > 10) {
    assert(x <= 10);
  }
  return 0;
}
