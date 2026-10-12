---
type: runbook
title: Yedekten geri yükleme
tested_on: postgres-17
---

# Yedekten geri yükleme

1. Servisi bakım kipine al.
2. Son doğrulanmış yedeği seç; özetini yedek kaydıyla karşılaştır.
3. Geri yükle ve bütünlük denetimini çalıştır.
4. Bakım kipinden çık; sonucu geri bildirim olarak kaydet.
