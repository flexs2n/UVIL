#include <stdlib.h>
#include <assert.h>

int main(void) {
  char buf[4];
  int i = __VERIFIER_nondet_int();
  buf[i] = 'x';
  return 0;
}
