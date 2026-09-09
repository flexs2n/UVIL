#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x <= 42) {
    assert(x + 1 <= 43);
  }
  return 0;
}
