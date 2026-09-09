#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x <= 2147483000) {
    assert(x + 100 <= 2147483647);
  }
  return 0;
}
