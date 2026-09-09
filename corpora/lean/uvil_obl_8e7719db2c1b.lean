theorem uvil_obl_8e7719db2c1b : ∀ (k : Int) (x : Int), ((k ≥ 1) ∧ (x ≥ (-k)) ∧ (x ≤ k)) → ((if (x < 0) then 0 else (if (x > k) then k else x)) ≤ k) := by omega
