#include <stdlib.h>
#include <assert.h>

int main(void) {
  int x = __VERIFIER_nondet_int();
  if (x > 0) {
    if (x < 10) {
      assert(x < 20);
    }
  }
  return 0;
}
