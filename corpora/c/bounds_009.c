#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a[10];
  int i = __VERIFIER_nondet_int();
  a[2 * i] = 1;
  return 0;
}
