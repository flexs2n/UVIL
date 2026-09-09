#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a[8];
  int b[8];
  int i = __VERIFIER_nondet_int();
  a[i] = 1;
  b[i] = 2;
  return a[i] + b[i];
}
