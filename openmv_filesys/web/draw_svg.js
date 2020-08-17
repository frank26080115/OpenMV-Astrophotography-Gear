function draw_svg(obj, imgdiv, zoom, reload_size, scale_vert, jpgdata, ghost_results)
{
    var svgNS = "http://www.w3.org/2000/svg";
    var dataw = 2592;
    var datah = 1944;

    var stars = obj["stars"];

    if (zoom <= 1) {
        zoom = 1;
    }

    if (reload_size) {
        while (imgdiv.firstChild) {
            imgdiv.removeChild(imgdiv.firstChild);
        }
    }

    var imgw = imgdiv.clientWidth;
    var imgh = Math.round((imgw / dataw) * datah);
    var imgscale = dataw / imgw;

    if (scale_vert)
    {
        var reduce = 0;
        while (imgh > screen.height * 0.8) {
            reduce += 10;
            imgw = imgdiv.clientWidth - reduce;
            imgh = Math.round((imgw / dataw) * datah);
            imgscale = dataw / imgw;
        }
    }

    imgscale /= zoom;

    var cent_x = settings["center_x"] / imgscale;
    var cent_y = settings["center_y"] / imgscale;
    var offset_x = 0, offset_y = 0;

    if (zoom > 1) {
        offset_x = cent_x - (imgw / 2);
        offset_y = cent_y - (imgh / 2);
    }

    // start the canvas with correct size
    var svgele = document.createElementNS(svgNS, "svg");
    while (imgdiv.firstChild) {
        imgdiv.removeChild(imgdiv.firstChild);
    }
    //imgdiv.setAttribute("height", imgh);
    imgdiv.style.height = imgh + "px";
    svgele.setAttribute("width", imgw);
    svgele.setAttribute("height", imgh);

    // draw a background rectangle that represents the background colour
    var bgrect = document.createElementNS(svgNS, "rect");
    bgrect.setAttribute("width", imgw);
    bgrect.setAttribute("height", imgh);
    bgrect.setAttribute("x", 0);
    bgrect.setAttribute("y", 0);
    var bgc = Math.round(obj["img_mean"] * 0.9).toString();
    bgrect.setAttribute("style", "fill:rgb(" + bgc + "," + bgc + "," + bgc + ");stroke:none;");
    svgele.appendChild(bgrect);

    // draw each star
    var maxr = 0;
    stars.forEach(function(ele, idx) {
        if (ele["r"] > maxr) {
            maxr = ele["r"];
        }
        if (jpgdata === false || jpgdata === null) {
            var cirele = document.createElementNS(svgNS, "circle");
            cirele.setAttribute("cx", Math.round((ele["cx"] / imgscale) - offset_x));
            cirele.setAttribute("cy", Math.round((ele["cy"] / imgscale) - offset_y));
            cirele.setAttribute("r", Math.round(ele["r"]));
            cirele.setAttribute("style", "fill:rgb(255,255,255);stroke:none;");
            svgele.appendChild(cirele);
        }
    });

    // we have jpg
    if (jpgdata !== false || jpgdata !== null) {
        var jpgele = document.createElementNS(svgNS, "image");
        jpgele.setAttribute("xlink:href", "data:image/jpg;base64," + jpgdata);
        jpgele.setAttribute("x", Math.round(-offset_x));
        jpgele.setAttribute("y", Math.round(-offset_y));
        jpgele.setAttribute("width", Math.round(dataw / imgscale));
        jpgele.setAttribute("height", Math.round(datah / imgscale));
        svgele.appendChild(jpgele);
    }

    var cline = document.createElementNS(svgNS, "line");
    cline.setAttribute("x1", Math.round(cent_x - offset_x));
    cline.setAttribute("x2", Math.round(cent_x - offset_x));
    cline.setAttribute("y1", Math.round(cent_y - offset_y + (imgh * 0.2)));
    cline.setAttribute("y2", Math.round(cent_y - offset_y - (imgh * 0.2)));
    cline.setAttribute("style", "stroke:yellow;stroke-width:1");
    svgele.appendChild(cline);
    cline = document.createElementNS(svgNS, "line");
    cline.setAttribute("y1", Math.round(cent_y - offset_y));
    cline.setAttribute("y2", Math.round(cent_y - offset_y));
    cline.setAttribute("x1", Math.round(cent_x - offset_x + (imgh * 0.2)));
    cline.setAttribute("x2", Math.round(cent_x - offset_x - (imgh * 0.2)));
    cline.setAttribute("style", "stroke:yellow;stroke-width:1");
    svgele.appendChild(cline);

    if (obj["solution"])
    {
        if (obj["star_x"] && obj["star_y"] && obj["pole_x"] && obj["pole_y"])
        {
            var sc_x = obj["star_x"];
            var sc_y = obj["star_y"];
            cirele = document.createElementNS(svgNS, "circle");
            cirele.setAttribute("cx", Math.round((sc_x / imgscale) - offset_x));
            cirele.setAttribute("cy", Math.round((sc_y / imgscale) - offset_y));
            cirele.setAttribute("r", 5);
            cirele.setAttribute("style", "fill:rgb(0,255,0);stroke:none;");
            svgele.appendChild(cirele);
            if (sc_x < 0 || sc_x > imgw || sc_y < 0 || sc_y > imgh)
            {
                var tline = document.createElementNS(svgNS, "line");
                tline.setAttribute("x1", Math.round(cent_x - offset_x));
                tline.setAttribute("x2", Math.round(sc_x - offset_x));
                tline.setAttribute("y1", Math.round(cent_y - offset_y));
                tline.setAttribute("y2", Math.round(sc_y - offset_y));
                tline.setAttribute("style", "stroke:green;stroke-width:1");
                svgele.appendChild(tline);
            }

            var poly = document.createElementNS(svgNS, "polygon");
            var px = (obj["pole_x"] / imgscale) - offset_x;
            var py = (obj["pole_y"] / imgscale) - offset_y;
            var len = 7, cor = 4;
            if (len < maxr) {
                len = maxr;
            }

            var refractionRotation = obj["rotation"] - obj["polar_clock"];
            var movedP = math_movePointTowards([px, py], [obj["refraction"] / imgscale, refractionRotation + 90.0]);
            px = movedP[0];
            py = movedP[1];

            var points = (px - 1).toString() + "," + (py - 1).toString() + " ";
            points += (px - 1).toString() + "," + (py - 1 - len).toString() + " ";
            points += (px - cor).toString() + "," + (py - cor).toString() + " ";
            points += (px - 1 - len).toString() + "," + (py - 1).toString() + " ";
            poly.setAttribute("points", points.trim());
            poly.setAttribute("style", "fill:rgb(255,0,0);stroke:none;");
            svgele.appendChild(poly);
            poly = document.createElementNS(svgNS, "polygon");
            points = (px + 1).toString() + "," + (py - 1).toString() + " ";
            points += (px + 1).toString() + "," + (py - 1 - len).toString() + " ";
            points += (px + cor).toString() + "," + (py - cor).toString() + " ";
            points += (px + 1 + len).toString() + "," + (py - 1).toString() + " ";
            poly.setAttribute("points", points.trim());
            poly.setAttribute("style", "fill:rgb(255,0,0);stroke:none;");
            svgele.appendChild(poly);
            poly = document.createElementNS(svgNS, "polygon");
            points = (px + 1).toString() + "," + (py + 1).toString() + " ";
            points += (px + 1).toString() + "," + (py + 1 + len).toString() + " ";
            points += (px + cor).toString() + "," + (py + cor).toString() + " ";
            points += (px + 1 + len).toString() + "," + (py + 1).toString() + " ";
            poly.setAttribute("points", points.trim());
            poly.setAttribute("style", "fill:rgb(255,0,0);stroke:none;");
            svgele.appendChild(poly);
            poly = document.createElementNS(svgNS, "polygon");
            points = (px - 1).toString() + "," + (py + 1).toString() + " ";
            points += (px - 1).toString() + "," + (py + 1 + len).toString() + " ";
            points += (px - cor).toString() + "," + (py + cor).toString() + " ";
            points += (px - 1 - len).toString() + "," + (py + 1).toString() + " ";
            poly.setAttribute("points", points.trim());
            poly.setAttribute("style", "fill:rgb(255,0,0);stroke:none;");
            svgele.appendChild(poly);

            if (px < 0 || px > imgw || py < 0 || py > imgh)
            {
                var tline = document.createElementNS(svgNS, "line");
                tline.setAttribute("x1", Math.round(cent_x - offset_x));
                tline.setAttribute("x2", Math.round(px - offset_x));
                tline.setAttribute("y1", Math.round(cent_y - offset_y));
                tline.setAttribute("y2", Math.round(py - offset_y));
                tline.setAttribute("style", "stroke:red;stroke-width:1");
                svgele.appendChild(tline);
            }

            if (ghost_results !== null && ghost_results !== false)
            {
                if (ghost_results.cent_x != null && ghost_results.cent_x != 0 && ghost_results.cent_y != null && ghost_results.cent_y != 0)
                {
                    var gline = document.createElementNS(svgNS, "line");
                    gline.setAttribute("x1", Math.round((ghost_results.cent_x / imgscale) - offset_x));
                    gline.setAttribute("x2", Math.round((ghost_results.mp1_x  / imgscale) - offset_x));
                    gline.setAttribute("y1", Math.round((ghost_results.cent_y / imgscale) - offset_y));
                    gline.setAttribute("y2", Math.round((ghost_results.mp1_y  / imgscale) - offset_y));
                    gline.setAttribute("style", "stroke:blue;stroke-width:1");
                    svgele.appendChild(gline);
                    gline = document.createElementNS(svgNS, "line");
                    gline.setAttribute("x1", Math.round((ghost_results.cent_x / imgscale) - offset_x));
                    gline.setAttribute("x2", Math.round((ghost_results.mp2_x  / imgscale) - offset_x));
                    gline.setAttribute("y1", Math.round((ghost_results.cent_y / imgscale) - offset_y));
                    gline.setAttribute("y2", Math.round((ghost_results.mp2_y  / imgscale) - offset_y));
                    gline.setAttribute("style", "stroke:blue;stroke-width:1");
                    svgele.appendChild(gline);
                    gline = document.createElementNS(svgNS, "line");
                    gline.setAttribute("x1", Math.round((ghost_results.star_x   / imgscale) - offset_x));
                    gline.setAttribute("x2", Math.round((ghost_results.ghost_sx / imgscale) - offset_x));
                    gline.setAttribute("y1", Math.round((ghost_results.star_y   / imgscale) - offset_y));
                    gline.setAttribute("y2", Math.round((ghost_results.ghost_sy / imgscale) - offset_y));
                    gline.setAttribute("style", "stroke:blue;stroke-width:1");
                    svgele.appendChild(gline);
                    gline = document.createElementNS(svgNS, "line");
                    gline.setAttribute("x1", Math.round((ghost_results.pole_x   / imgscale) - offset_x));
                    gline.setAttribute("x2", Math.round((ghost_results.ghost_px / imgscale) - offset_x));
                    gline.setAttribute("y1", Math.round((ghost_results.pole_y   / imgscale) - offset_y));
                    gline.setAttribute("y2", Math.round((ghost_results.ghost_py / imgscale) - offset_y));
                    gline.setAttribute("style", "stroke:blue;stroke-width:1");
                    svgele.appendChild(gline);
                }
            }
        }
    }

    if (ghost !== null && ghost !== false)
    {
        var gcir = document.createElementNS(svgNS, "circle");
        gcir.setAttribute("cx", Math.round((ghost.star_x / imgscale) - offset_x));
        gcir.setAttribute("cy", Math.round((ghost.star_y / imgscale) - offset_y));
        gcir.setAttribute("r", 3);
        gcir.setAttribute("style", "stroke:blue;stroke-width:2");
        svgele.appendChild(gcir);
        gcir = document.createElementNS(svgNS, "circle");
        gcir.setAttribute("cx", Math.round((ghost.pole_x / imgscale) - offset_x));
        gcir.setAttribute("cy", Math.round((ghost.pole_y / imgscale) - offset_y));
        gcir.setAttribute("r", 3);
        gcir.setAttribute("style", "stroke:blue;stroke-width:2");
        svgele.appendChild(gcir);
    }

    return svgele;
}