# /// script
# requires-python = ">=3.12"
# dependencies = ["marimo"]
# ///

"""鸢尾花数据集分析 - Iris Dataset Analysis (Self-contained)"""
# marimo.App (for directory scanner)

import marimo

app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        """
        # 🌸 鸢尾花数据集分析
        
        **数据集来源**: UCI Machine Learning Repository (内嵌数据)
        
        鸢尾花数据集是机器学习领域最著名的数据集之一，包含三种鸢尾花的测量数据：
        - **Setosa** (山鸢尾)
        - **Versicolor** (变色鸢尾)
        - **Virginica** (维吉尼亚鸢尾)
        
        每种花有 50 个样本，共 150 条记录。
        """
    )
    return


@app.cell
def _():
    # 内嵌鸢尾花数据（无需网络请求）
    iris_data = [
        # Setosa (50 samples)
        {"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2, "species": "Setosa"},
        {"sepal_length": 4.9, "sepal_width": 3.0, "petal_length": 1.4, "petal_width": 0.2, "species": "Setosa"},
        {"sepal_length": 4.7, "sepal_width": 3.2, "petal_length": 1.3, "petal_width": 0.2, "species": "Setosa"},
        {"sepal_length": 4.6, "sepal_width": 3.1, "petal_length": 1.5, "petal_width": 0.2, "species": "Setosa"},
        {"sepal_length": 5.0, "sepal_width": 3.6, "petal_length": 1.4, "petal_width": 0.2, "species": "Setosa"},
        {"sepal_length": 5.4, "sepal_width": 3.9, "petal_length": 1.7, "petal_width": 0.4, "species": "Setosa"},
        {"sepal_length": 4.6, "sepal_width": 3.4, "petal_length": 1.4, "petal_width": 0.3, "species": "Setosa"},
        {"sepal_length": 5.0, "sepal_width": 3.4, "petal_length": 1.5, "petal_width": 0.2, "species": "Setosa"},
        {"sepal_length": 4.4, "sepal_width": 2.9, "petal_length": 1.4, "petal_width": 0.2, "species": "Setosa"},
        {"sepal_length": 4.9, "sepal_width": 3.1, "petal_length": 1.5, "petal_width": 0.1, "species": "Setosa"},
        # Versicolor (50 samples - subset)
        {"sepal_length": 7.0, "sepal_width": 3.2, "petal_length": 4.7, "petal_width": 1.4, "species": "Versicolor"},
        {"sepal_length": 6.4, "sepal_width": 3.2, "petal_length": 4.5, "petal_width": 1.5, "species": "Versicolor"},
        {"sepal_length": 6.9, "sepal_width": 3.1, "petal_length": 4.9, "petal_width": 1.5, "species": "Versicolor"},
        {"sepal_length": 5.5, "sepal_width": 2.3, "petal_length": 4.0, "petal_width": 1.3, "species": "Versicolor"},
        {"sepal_length": 6.5, "sepal_width": 2.8, "petal_length": 4.6, "petal_width": 1.5, "species": "Versicolor"},
        {"sepal_length": 5.7, "sepal_width": 2.8, "petal_length": 4.5, "petal_width": 1.3, "species": "Versicolor"},
        {"sepal_length": 6.3, "sepal_width": 3.3, "petal_length": 4.7, "petal_width": 1.6, "species": "Versicolor"},
        {"sepal_length": 4.9, "sepal_width": 2.4, "petal_length": 3.3, "petal_width": 1.0, "species": "Versicolor"},
        {"sepal_length": 6.6, "sepal_width": 2.9, "petal_length": 4.6, "petal_width": 1.3, "species": "Versicolor"},
        {"sepal_length": 5.2, "sepal_width": 2.7, "petal_length": 3.9, "petal_width": 1.4, "species": "Versicolor"},
        # Virginica (50 samples - subset)
        {"sepal_length": 6.3, "sepal_width": 3.3, "petal_length": 6.0, "petal_width": 2.5, "species": "Virginica"},
        {"sepal_length": 5.8, "sepal_width": 2.7, "petal_length": 5.1, "petal_width": 1.9, "species": "Virginica"},
        {"sepal_length": 7.1, "sepal_width": 3.0, "petal_length": 5.9, "petal_width": 2.1, "species": "Virginica"},
        {"sepal_length": 6.3, "sepal_width": 2.9, "petal_length": 5.6, "petal_width": 1.8, "species": "Virginica"},
        {"sepal_length": 6.5, "sepal_width": 3.0, "petal_length": 5.8, "petal_width": 2.2, "species": "Virginica"},
        {"sepal_length": 7.6, "sepal_width": 3.0, "petal_length": 6.6, "petal_width": 2.1, "species": "Virginica"},
        {"sepal_length": 4.9, "sepal_width": 2.5, "petal_length": 4.5, "petal_width": 1.7, "species": "Virginica"},
        {"sepal_length": 7.3, "sepal_width": 2.9, "petal_length": 6.3, "petal_width": 1.8, "species": "Virginica"},
        {"sepal_length": 6.7, "sepal_width": 2.5, "petal_length": 5.8, "petal_width": 1.8, "species": "Virginica"},
        {"sepal_length": 7.2, "sepal_width": 3.6, "petal_length": 6.1, "petal_width": 2.5, "species": "Virginica"},
    ]
    return (iris_data,)


@app.cell
def _(iris_data, mo):
    # 计算统计数据
    _species_counts = {}
    _feature_sums = {"sepal_length": 0, "sepal_width": 0, "petal_length": 0, "petal_width": 0}
    _feature_counts = {"sepal_length": 0, "sepal_width": 0, "petal_length": 0, "petal_width": 0}
    
    for _row in iris_data:
        _sp = _row["species"]
        _species_counts[_sp] = _species_counts.get(_sp, 0) + 1
        for _feat in _feature_sums:
            _feature_sums[_feat] += _row[_feat]
            _feature_counts[_feat] += 1
    
    _feature_avgs = {f: _feature_sums[f] / _feature_counts[f] for f in _feature_sums}
    
    stats_md = mo.md(f"""
    ## 📊 数据集概览
    
    | 属性 | 值 |
    | --- | --- |
    | **样本数量** | {len(iris_data)} |
    | **特征数量** | 4 |
    | **类别数量** | {len(_species_counts)} |
    | **类别分布** | {', '.join(f'{k}: {v}' for k, v in _species_counts.items())} |
    
    ### 特征平均值
    | 特征 | 平均值 (cm) |
    | --- | --- |
    | 花萼长度 | {_feature_avgs['sepal_length']:.2f} |
    | 花萼宽度 | {_feature_avgs['sepal_width']:.2f} |
    | 花瓣长度 | {_feature_avgs['petal_length']:.2f} |
    | 花瓣宽度 | {_feature_avgs['petal_width']:.2f} |
    """)
    stats_md
    return


@app.cell
def _(iris_data, mo):
    # 数据表格预览
    preview_table = mo.ui.table(
        iris_data[:15],
        label="数据预览 (前15行)",
        selection=None
    )
    preview_table
    return


@app.cell
def _(iris_data, mo):
    # 类别分布 SVG 柱状图
    _species_counts = {}
    for _row in iris_data:
        _sp = _row["species"]
        _species_counts[_sp] = _species_counts.get(_sp, 0) + 1
    
    _max_count = max(_species_counts.values())
    _colors = {"Setosa": "#FF6B6B", "Versicolor": "#4ECDC4", "Virginica": "#45B7D1"}
    
    _bars = []
    _y = 30
    for _species, _count in _species_counts.items():
        _width = int((_count / _max_count) * 200)
        _bars.append(
            f"""
            <text x="10" y="{_y}" font-size="13" fill="#334155">{_species}</text>
            <rect x="100" y="{_y - 14}" rx="6" ry="6" width="{_width}" height="20" fill="{_colors.get(_species, '#2563eb')}"></rect>
            <text x="{110 + _width}" y="{_y}" font-size="12" fill="#0f172a" font-weight="bold">{_count}</text>
            """
        )
        _y += 40
    
    _svg1 = f"""
    <svg width="350" height="{_y + 10}" viewBox="0 0 350 {_y + 10}" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8fafc"></rect>
      <text x="10" y="15" font-size="14" font-weight="bold" fill="#1e293b">类别分布</text>
      {''.join(_bars)}
    </svg>
    """
    
    mo.Html(_svg1)
    return


@app.cell
def _(iris_data, mo):
    # 花瓣长度 vs 花瓣宽度 散点图 (SVG)
    _colors2 = {"Setosa": "#FF6B6B", "Versicolor": "#4ECDC4", "Virginica": "#45B7D1"}
    
    # 找到数据范围
    _petal_lengths = [r["petal_length"] for r in iris_data]
    _petal_widths = [r["petal_width"] for r in iris_data]
    _min_pl, _max_pl = min(_petal_lengths), max(_petal_lengths)
    _min_pw, _max_pw = min(_petal_widths), max(_petal_widths)
    
    # 映射到 SVG 坐标
    def _scale(_val, _min_val, _max_val, _new_min, _new_max):
        if _max_val == _min_val:
            return _new_min
        return _new_min + (_val - _min_val) / (_max_val - _min_val) * (_new_max - _new_min)
    
    _points = []
    for _row in iris_data:
        _x = _scale(_row["petal_length"], _min_pl, _max_pl, 50, 450)
        _y = _scale(_row["petal_width"], _max_pw, _min_pw, 30, 330)  # Y轴反转
        _color = _colors2.get(_row["species"], "#999")
        _points.append(f'<circle cx="{_x:.1f}" cy="{_y:.1f}" r="6" fill="{_color}" stroke="white" stroke-width="1.5" opacity="0.8"/>')
    
    # 图例
    _legend_y = 360
    _legend_items = [f'<circle cx="{50 + i * 120}" cy="{_legend_y}" r="5" fill="{c}"/><text x="{60 + i * 120}" y="{_legend_y + 4}" font-size="11" fill="#334155">{s}</text>' for i, (s, c) in enumerate(_colors2.items())]
    
    _svg2 = f"""
    <svg width="500" height="390" viewBox="0 0 500 390" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8fafc"></rect>
      <text x="230" y="20" font-size="14" font-weight="bold" fill="#1e293b">花瓣长度 vs 花瓣宽度</text>
      
      <!-- 坐标轴 -->
      <line x1="50" y1="330" x2="450" y2="330" stroke="#cbd5e1" stroke-width="1"/>
      <line x1="50" y1="30" x2="50" y2="330" stroke="#cbd5e1" stroke-width="1"/>
      
      <!-- X轴标签 -->
      <text x="50" y="350" font-size="10" fill="#64748b">{_min_pl:.1f}</text>
      <text x="440" y="350" font-size="10" fill="#64748b">{_max_pl:.1f}</text>
      <text x="220" y="350" font-size="11" fill="#334155">花瓣长度 (cm)</text>
      
      <!-- Y轴标签 -->
      <text x="20" y="330" font-size="10" fill="#64748b">{_min_pw:.1f}</text>
      <text x="20" y="35" font-size="10" fill="#64748b">{_max_pw:.1f}</text>
      <text x="15" y="180" font-size="11" fill="#334155" transform="rotate(-90, 15, 180)">花瓣宽度 (cm)</text>
      
      <!-- 数据点 -->
      {''.join(_points)}
      
      <!-- 图例 -->
      {''.join(_legend_items)}
    </svg>
    """
    
    mo.Html(_svg2)
    return


@app.cell
def _(iris_data, mo):
    # 按类别计算特征平均值
    _species_data = {"Setosa": [], "Versicolor": [], "Virginica": []}
    for _row in iris_data:
        _species_data[_row["species"]].append(_row)
    
    _species_avgs = {}
    for _sp, _rows in _species_data.items():
        if _rows:
            _species_avgs[_sp] = {
                "sepal_length": sum(r["sepal_length"] for r in _rows) / len(_rows),
                "sepal_width": sum(r["sepal_width"] for r in _rows) / len(_rows),
                "petal_length": sum(r["petal_length"] for r in _rows) / len(_rows),
                "petal_width": sum(r["petal_width"] for r in _rows) / len(_rows),
            }
    
    # 分组柱状图
    _colors3 = {"Setosa": "#FF6B6B", "Versicolor": "#4ECDC4", "Virginica": "#45B7D1"}
    _features = ["sepal_length", "sepal_width", "petal_length", "petal_width"]
    _feature_names = ["花萼长度", "花萼宽度", "花瓣长度", "花瓣宽度"]
    
    _bar_groups = []
    _x_pos = 60
    for _i, _feat in enumerate(_features):
        _feat_name = _feature_names[_i]
        _bar_group = f'<text x="{_x_pos + 10}" y="270" font-size="10" fill="#334155">{_feat_name}</text>'
        for _j, _sp_name in enumerate(["Setosa", "Versicolor", "Virginica"]):
            _val = _species_avgs[_sp_name][_feat]
            _height = int((_val / 10) * 200)  # 缩放到 0-10 cm 范围
            _bar_x = _x_pos + _j * 25
            _bar_group += f'<rect x="{_bar_x}" y="{250 - _height}" width="20" height="{_height}" fill="{_colors3[_sp_name]}" rx="3"/>'
        _bar_groups.append(_bar_group)
        _x_pos += 90
    
    # 图例
    _legend2 = ''.join([f'<rect x="{380 + i * 70}" y="20" width="12" height="12" fill="{c}"/><text x="{395 + i * 70}" y="30" font-size="10" fill="#334155">{s}</text>' for i, (s, c) in enumerate(_colors3.items())])
    
    _svg3 = f"""
    <svg width="500" height="300" viewBox="0 0 500 300" xmlns="http://www.w3.org/2000/svg">
      <rect width="100%" height="100%" fill="#f8fafc"></rect>
      <text x="160" y="20" font-size="14" font-weight="bold" fill="#1e293b">各类别特征平均值对比</text>
      
      <!-- Y轴 -->
      <line x1="50" y1="50" x2="50" y2="250" stroke="#cbd5e1" stroke-width="1"/>
      <line x1="50" y1="250" x2="420" y2="250" stroke="#cbd5e1" stroke-width="1"/>
      <text x="25" y="255" font-size="9" fill="#64748b">0</text>
      <text x="25" y="55" font-size="9" fill="#64748b">10</text>
      <text x="15" y="150" font-size="10" fill="#334155" transform="rotate(-90, 15, 150)">cm</text>
      
      <!-- 柱状图组 -->
      {''.join(_bar_groups)}
      
      <!-- 图例 -->
      {_legend2}
    </svg>
    """
    
    mo.Html(_svg3)
    return


@app.cell
def _(mo):
    conclusion = mo.md("""
    ## 📝 分析结论
    
    ### 1. 数据集特点
    - 鸢尾花数据集包含 **150 个样本**（本示例展示30条），分为 **3 个类别**
    - 4 个数值特征：花萼长度、花萼宽度、花瓣长度、花瓣宽度
    - 数据完整，**无缺失值**
    
    ### 2. 特征关系
    - **花瓣长度与花瓣宽度** 高度相关，能有效区分不同类别
    - **Setosa** 明显与其他两类区分开，花瓣小且短
    - **Versicolor 和 Virginica** 有一定重叠，但 Virginica 整体更大
    
    ### 3. 分类难度
    - **Setosa**: 容易区分（线性可分）
    - **Versicolor**: 中等难度
    - **Virginica**: 与 Versicolor 有部分重叠
    
    ### 4. 适用场景
    此数据集非常适合用于：
    - 分类算法入门（KNN、SVM、决策树等）
    - 数据可视化教学
    - 特征工程实践
    
    ---
    💡 **提示**: 本可视化使用纯 SVG 实现，无需外部依赖，可离线运行。
    """)
    conclusion
    return


if __name__ == "__main__":
    app.run()