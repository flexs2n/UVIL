#include <stdlib.h>
#include <assert.h>

int main(void) {
  int a = __VERIFIER_nondet_int();
  int s = 1;
  for (int i = 0; i < 26; i++) {
    s = (s * 41 + a * a) % 1000003;
  }
  assert(s != 11);
  return 0;
}
