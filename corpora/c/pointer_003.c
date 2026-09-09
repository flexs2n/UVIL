#include <stdlib.h>
#include <assert.h>

int main(void) {
  int *p = (int *)malloc(sizeof(int));
  free(p);
  int z = *p;
  return z;
}
