#include <stdlib.h>
#include <assert.h>

int main(void) {
  int s = 0;
  for (int i = 0; i < 4; i++) {
    s = s + i;
  }
  assert(s == 6);
  return 0;
}
