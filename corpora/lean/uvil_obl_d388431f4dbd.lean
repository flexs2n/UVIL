theorem uvil_obl_d388431f4dbd : ∀ (k : Int) (x : Int), ((k ≥ 1) ∧ (x ≥ (-k)) ∧ (x ≤ k)) → ((if (x < 0) then 0 else (if (x > k) then k else x)) ≥ 0) := by omega
