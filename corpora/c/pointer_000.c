#include <stdlib.h>
#include <assert.h>

int main(void) {
  int *p = (int *)malloc(sizeof(int));
  if (p != 0) {
    *p = 5;
    int z = *p;
    assert(z == 5);
  }
  free(p);
  return 0;
}
