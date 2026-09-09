#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x <= -2) {
    assert(x + 1 >= 0);
  }
  return 0;
}
