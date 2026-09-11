use vstd::prelude::*;

fn main() {}

verus! {

fn gen_add_id(x: i32)
    requires x >= 0,
    ensures x + 0 == x,
{
}

}
