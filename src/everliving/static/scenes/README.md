# 場景圖 — 丟一張進來,下一次來訪畫面就換掉

這個資料夾是**設計文件第七節〈`scene` 標籤與預先生成圖庫〉**講的那件事:
「一組**固定場景圖**……用任何工具做一次存成檔案即可,**顯示端查表貼圖**」。
per-call 成本是**零**,不接任何圖片 API。

**沒有檔案的時候什麼都不會壞**——畫面退回程式自己畫的向量場景,跟今天一模一樣。
**檔案載不出來也一樣**:那個 `<image>` 元素畫不出東西,底下的向量圖就透出來。

---

## 檔名規則

```
<場景>.webp             ← 這個地方的通用圖
<場景>-s<階段>.webp     ← 這個地方在世界某個階段的樣子(有就優先用)
```

**場景只有六個,是封閉清單**(模型不准自己發明,`agent_loop.py:81`):

| 檔名 | 是什麼 |
|---|---|
| `工作間` | 他自己的工作檯。**最重要的一張**,開場預設就是這裡 |
| `回收場` | 撿零件的地方。世界壞到第 14 天之後會變成開場 |
| `配電所` | 一直跳電的地方。第 45 天之後 |
| `潮線` | 水本身。第 150 天之後 |
| `機器廠` | 還沒當過開場,但模型可以在對話裡去 |
| `港城` | 全景,也是認不得的場景時的退路 |

**副檔名可以是** `.webp` / `.avif` / `.png` / `.jpg`。同名時照這個順序挑。

**只畫得出一張就只放一張。** 半套是預期狀態:某個地方只有通用圖,它每個階段都用那張——
比全套差,但**比開天窗好得多**。

## 階段(世界時鐘)

`-s0` 到 `-s4`。階段是**世界存在了幾天**換算的,一路只會往壞的走:

| 階段 | 第幾天起 | 那陣子長什麼樣(這段文字也會餵給模型) |
|---|---|---|
| `s0` | 0 | 水濾一次就能喝。鐵件放著不管,一個月才起一層薄鏽 |
| `s1` | 4 | 水要濾兩次,濾芯泛黃。零件開始出現咬得比較深的鏽點 |
| `s2` | 14 | 濾芯換得比以前勤,夜裡喉嚨會癢。街上戴口罩的人變多 |
| `s3` | 45 | 水要放一夜讓它沉,只有上層敢用。限電從一週一次變三次 |
| `s4` | 150 | 濾水花的時間比修東西還長。隔壁老人搬進了模擬倉 |

**先做 `工作間` 的 s0 / s2 / s4 三張**就看得出時間在走了,不用一次做滿 30 張。

## 尺寸

- **比例 1000 × 420(約 2.38:1)**,建議實際做 **2000 × 840**
- 貼上去是 `slice`(填滿後裁切),而且外層容器高度會隨視窗變——
  **重要的東西放中間 80%,邊緣會被吃掉**
- 檔案控制在 **500KB 以內**;`.webp` 品質 80 通常就夠

## 加圖之後不用重開伺服器

檔案清單是**每次請求現讀**的。丟檔案 → 重新整理 → 就看到了。

---

# 生圖 prompt

**風格先講一次,每一張都套用。** 這段是照設計文件第十一節的世界寫的,
不要改成別的調性,不然六張圖會像六個不同的遊戲。

> **共用風格**
>
> ```
> Muted painterly digital illustration, near-monochrome dark teal-black base
> (#0b1a21) with pale salt-grey highlights, one warm sodium-orange light source
> and small rust-red accents. Overcast, humid, post-industrial. Cinematic wide
> composition 2.38:1, low camera, quiet and lived-in — nobody is fighting, this
> is a place where one person maintains things. No text, no logos, no UI, no
> people's faces. Hand-built and patched, not sleek sci-fi: bolted plates,
> salvaged parts, cable runs, water stains, corrosion.
> ```

**注意兩件事**:
1. **不要畫人。** 陌洲不出現在場景圖裡——他在文字裡。畫了人之後每一句話都會跟那張臉打架
2. **不要放字。** 生成的字幾乎都是亂碼,而且畫面上已經有真的中文標籤了

## 工作間(最先做這張)

```
A cramped repair workshop at night, seen across the workbench. A single sodium
lamp on a jointed arm throws a warm pool of light over a scarred steel bench:
a dismantled water filter housing, hand tools laid in a row, a bench vice, coils
of wire, a jar of screws. Beyond the bench a rain-streaked window shows a
half-sunken city as a dark silhouette, almost black. The light falls off hard —
the bench is bright, the room is dim, the window is nearly black.
```

**階段變體改的是檯面上的東西,不是構圖**:
- `-s0`:零件乾淨,金屬只有薄薄一層灰
- `-s2`:濾芯泛黃堆在角落,工具握把磨損,檯面有水痕
- `-s4`:檯面堆滿別人不要的零件(鄰居搬進模擬倉留下的),燈光偏暗、像在限電

## 回收場

```
An outdoor salvage yard at dusk, ankle-deep in standing water. Sorted heaps of
corroded machine parts under sagging tarpaulins, a gantry crane silhouette, a
line of salvaged cabinets. One work light on a pole is the only warm source.
Rust bleeds orange into the puddles.
```

## 配電所

```
The interior of a small electrical substation. Rows of tall grey switchgear
cabinets, some panels open showing bus bars and hand-labelled terminal blocks.
One cabinet's indicator lamps are lit; the rest are dead. A torch beam or an
emergency lamp is the only warm light. Cables run along the floor over a drain
grating with water in it.
```

## 潮線

```
The waterline of a half-sunken port city at low tide. Concrete piles and the
upper floors of drowned buildings stand out of flat grey water. Tide marks and
weed stain everything to the same height. A narrow catwalk of scaffold planks
runs out over the water. Far off, one orange light on a mast.
```

## 機器廠

```
The floor of an old machine works, mostly cold. Overhead line shafts and belt
drives, lathes under dust sheets, a single bay still in use with a warm lamp
over it. High dirty clerestory windows let in flat grey daylight from above.
```

## 港城

```
A wide establishing view of a half-sunken port city under heavy overcast.
Towers standing in water to the third floor, walkways and cable runs strung
between them, small boats. Most windows dark, a scattering of warm ones. A red
beacon on the tallest mast. Rain haze flattens the distance.
```

---

## 一件要知道的取捨

設計文件第七節寫過**當時**不做這個的理由:

> **同時加圖會讓 H-1 測不準**——分不清打動你的是敘事還是圖。

那條顧慮仍然成立。**人類 2026-08-08 在看過畫面之後選了圖片素材**,所以這是他的決定,
記在這裡不是要翻案,是要讓之後跑 H-1 的人知道:**這一版的留存數字裡混著圖的效果。**
