#include <stdlib.h>
#include <assert.h>

int main(void) {
  struct node { int v; struct node *next; };
  struct node *b = (struct node *)malloc(sizeof(struct node));
  struct node *a = (struct node *)malloc(sizeof(struct node));
  if (a != 0 && b != 0) {
    a->v = 1;
    b->v = 2;
    a->next = b;
    b->next = 0;
    assert(a->next->v == 2);
  }
  free(a);
  free(b);
  return 0;
}
