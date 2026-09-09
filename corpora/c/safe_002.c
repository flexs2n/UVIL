#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x >= 7) {
    assert(x - 7 >= 0);
  }
  return 0;
}
