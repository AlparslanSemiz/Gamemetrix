# Light Checkstyle Principles

Bu kuralların amacı kodu gereksiz şekilde akademik veya bürokratik hale getirmek değil; okunabilir, test edilebilir, debug edilebilir ve büyütülebilir tutmaktır.

## 1. Okunabilirlik

Kod ilk bakışta ne yaptığını anlatmalıdır. İsimler anlamlı olmalı; metot, değişken ve sınıf adları niyeti göstermelidir. Tek satırda birden fazla statement yazılmamalı, aynı satırda birden fazla değişken declare edilmemelidir. Braces her zaman kullanılmalıdır; tek satırlık `if`, `for`, `while` bloklarında bile `{}` bırakılmamalıdır.

## 2. Küçük ve tek sorumluluklu parçalar

Metotlar ideal olarak kısa kalmalı, birden fazla işi aynı anda yapmamalıdır. Bir metot 80 satırı geçiyorsa veya çok fazla nested `if/for/try` içeriyorsa önce bölünmelidir. Parametre sayısı çok artıyorsa veri modeli, DTO veya küçük bir abstraction ihtiyacı değerlendirilmelidir.

## 3. Tutarlı dosya ve sınıf yapısı

Bir Java dosyasında tek top-level class olmalıdır. Dosya adı ile ana class adı uyumlu olmalıdır. Package isimleri küçük harfli ve tutarlı olmalıdır. Utility class varsa constructor private olmalıdır.

## 4. Temiz import ve bağımlılık kullanımı

Star import kullanılmamalıdır. Kullanılmayan ve redundant importlar temizlenmelidir. Eski Java tipleri yerine modern karşılıklar tercih edilmelidir; örneğin `java.util.Date`, `Vector`, `Hashtable`, `Stack` kullanılmamalıdır.

## 5. Mantıksal doğruluk

`equals` override ediliyorsa `hashCode` da override edilmelidir. String karşılaştırmaları `==` ile yapılmamalıdır. Boolean ifadeler gereksiz karmaşık tutulmamalıdır. Loop control variable gereksiz şekilde değiştirilmemeli, parametreler method içinde yeniden assign edilmemelidir.

## 6. Exception handling

Boş `catch` blokları kullanılmamalıdır. Çok genel `Exception`, `Throwable`, `Error` yakalamaktan veya fırlatmaktan kaçınılmalıdır. Bir metodun çok fazla exception throw etmesi genellikle sorumlulukların ayrılması gerektiğini gösterir.

## 7. Format ve hijyen

Satır uzunluğu 140 karakteri geçmemelidir. Dosya çok büyüyorsa sınıfın sorumluluğu kontrol edilmelidir. Tab yerine space kullanılmalıdır. Dosya sonunda newline olmalıdır. `TODO`, `FIXME`, `XXX` bırakılabilir ama görünür uyarı olarak kalmalıdır.

## 8. Bilinçli esneklik

Bu kurallar mutlak doğru değil, kalite sinyalidir. Bir uyarı gerçek bir tasarım tercihi nedeniyle ihlal ediliyorsa, önce gerekçesi anlaşılmalı; sonra gerekiyorsa lokal ve açıklamalı şekilde istisna uygulanmalıdır. Ama kodu anlamadan uyarı susturulmamalıdır.
