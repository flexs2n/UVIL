#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  int y = x + 1;
  if (x == 2147483647) {
    assert(y > x);
  }
  return 0;
}
