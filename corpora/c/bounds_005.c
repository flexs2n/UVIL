#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a[10];
  int i = __VERIFIER_nondet_int();
  a[i + 3] = 1;
  return 0;
}
