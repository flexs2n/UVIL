#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a[4];
  int x = __VERIFIER_nondet_int();
  int y = __VERIFIER_nondet_int();
  a[x * y] = 1;
  return 0;
}
