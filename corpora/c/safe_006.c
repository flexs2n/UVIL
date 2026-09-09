#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  int y = x + 1;
  int z = y + 1;
  if (x >= 0) {
    assert(z == x + 2);
  }
  return 0;
}
