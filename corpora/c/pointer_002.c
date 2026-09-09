#include <stdlib.h>
#include <assert.h>

int main(void) {
  int *p = (int *)malloc(10 * sizeof(int));
  if (p != 0) {
    for (int i = 0; i < 10; i++) {
      p[i] = i;
    }
    assert(p[9] == 9);
  }
  free(p);
  return 0;
}
