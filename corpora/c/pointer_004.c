#include <stdlib.h>
#include <assert.h>

int main(void) {
  int *p = (int *)malloc(sizeof(int));
  *p = 5;
  int z = *p;
  free(p);
  return z;
}
