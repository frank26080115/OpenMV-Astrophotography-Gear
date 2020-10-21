var svgNS = "http://www.w3.org/2000/svg";

function get_draw_scale(zoom, scale_vert)
{
    var wrapdiv = document.getElementById("viewme");
    var imgw = wrapdiv.clientWidth;
    var imgh = Math.round((imgw / dataw) * datah);
    var imgscale = dataw / imgw;

    // scale_vert will make the image fit to the vertical space
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

    // apply the zoom level
    imgscale /= zoom;
    return [dataw, datah, imgw, imgh, imgscale];
}

function get_zoom()
{
    var zoom = 1;
    if ($("#viewmode-2").prop("checked")) {
        zoom = 2;
    }
    if ($("#viewmode-3").prop("checked")) {
        zoom = 4;
    }
    if ($("#viewmode-4").prop("checked")) {
        zoom = 8;
    }
    return zoom;
}

function draw_svg(obj, zoom, need_reload, scale_vert, simpcali_results)
{
    var wrapdiv = document.getElementById("viewme");
    var imgdiv = document.getElementById("viewmesvg");

    var stars = obj["stars"];

    if (zoom <= 1) {
        zoom = 1;
    }

    if (need_reload) {
        while (imgdiv.firstChild) {
            imgdiv.removeChild(imgdiv.firstChild);
        }
    }

    d = get_draw_scale(zoom, scale_vert);
    var dataw = d[0];
    var datah = d[1];
    var imgw = d[2];
    var imgh = d[3];
    var imgscale = d[4];

    var cent_x = settings["center_x"] / imgscale;
    var cent_y = settings["center_y"] / imgscale;
    var offset_x = 0, offset_y = 0;

    if (zoom > 1)
    {
        offset_x = cent_x - (imgw / 2);
        offset_y = cent_y - (imgh / 2);
        var testxd = imgw / (2 * zoom);
        var testyd = imgh / (2 * zoom);
        while (true)
        {
            var ch_x = cent_x - offset_x;
            var ch_y = cent_y - offset_y;
            if (ch_x - testxd < 0) {
                offset_x -= 1;
            }
            else if (ch_x + testxd > imgw) {
                offset_x += 1;
            }
            else if (ch_y - testyd < 0) {
                offset_y -= 1;
            }
            else if (ch_y + testyd > imgh) {
                offset_y += 1;
            }
            else {
                break;
            }
        }
    }

    // start the canvas with correct size
    var svgele = document.createElementNS(svgNS, "svg");
    while (imgdiv.firstChild) {
        imgdiv.removeChild(imgdiv.firstChild);
    }
    //imgdiv.setAttribute("height", imgh);
    //imgdiv.style.height  = imgh + "px";
    imgdiv.style.top  = "-" + imgh + "px";
    wrapdiv.style.height = imgh + "px";

    var cirele;

    svgele.setAttribute("id", "imgsvg");
    svgele.setAttribute("width", imgw);
    svgele.setAttribute("height", imgh);

    svgele.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svgele.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");

    // draw a background rectangle that represents the background colour
    var bgrect = document.createElementNS(svgNS, "rect");
    bgrect.setAttribute("width", imgw);
    bgrect.setAttribute("height", imgh);
    bgrect.setAttribute("x", 0);
    bgrect.setAttribute("y", 0);
    var bgc = Math.round(obj["img_mean"] * 0.9).toString();
    bgrect.setAttribute("style", "fill:rgb(" + bgc + "," + bgc + "," + bgc + ");stroke:none;");
    svgele.appendChild(bgrect);

    var maxr = 0; // find the biggest star, used for other things later
    var minr = 9999;
    stars.forEach(function(ele, idx) {
        if (ele["r"] > maxr) {
            maxr = ele["r"];
        }
        if (ele["r"] < minr) {
            minr = ele["r"];
        }
    });

    // draw each star
    stars.forEach(function(ele, idx) {
        var cx = ele["cx"];
        var cy = ele["cy"];

        var ishot = checkHotPixel(ele);
        if (ishot == false)
        {
            var drawn_rad = math_mapStarRadius(ele["r"], minr, maxr, imgh);
            cirele = document.createElementNS(svgNS, "circle");
            cirele.setAttribute("cx", Math.round((cx / imgscale) - offset_x));
            cirele.setAttribute("cy", Math.round((cy / imgscale) - offset_y));
            cirele.setAttribute("r", drawn_rad);
            cirele.setAttribute("style", "fill:rgb(255,255,255);stroke:none;");
            cirele.setAttribute("onclick", "star_onclick(" + cx + ", " + cy + ");");
            svgele.appendChild(cirele);

            // draw one that's bigger so that it's easier to click
            // check distance to another nearby star to make sure we don't draw an overlapping clickable circle
            var mindist = -1;
            stars.forEach(function(ele2, idx2) {
                if (idx == idx2) {
                    return;
                }
                v = math_getVector([ele["cx"],ele["cy"]], [ele2["cx"],ele2["cy"]]);
                if (mindist < 0 || v[0] < mindist) {
                    mindist = v[0];
                }
            });
            mindist = mindist / imgscale / 2;

            // establish minimum and maximum size of 
            if (mindist > drawn_rad)
            {
                drawn_rad = mindist;
                if (drawn_rad > imgh / 20) {
                    drawn_rad = imgh / 20;
                }
                cirele = document.createElementNS(svgNS, "circle");
                cirele.setAttribute("cx", Math.round((cx / imgscale) - offset_x));
                cirele.setAttribute("cy", Math.round((cy / imgscale) - offset_y));
                cirele.setAttribute("r", drawn_rad);
                cirele.setAttribute("style", "fill:rgb(255,255,255, 0.001);stroke:none;");
                cirele.setAttribute("onclick", "star_onclick(" + cx + ", " + cy + ");");
                svgele.appendChild(cirele);
            }
        }
    });

    if (platesolve_start_x > 0 && platesolve_start_y > 0)
    {
        cirele = document.createElementNS(svgNS, "circle");
        cirele.setAttribute("cx", Math.round((platesolve_start_x / imgscale) - offset_x));
        cirele.setAttribute("cy", Math.round((platesolve_start_y / imgscale) - offset_y));
        cirele.setAttribute("r", imgh / 20);
        cirele.setAttribute("style", "fill:none;stroke:yellow;stroke-width:1");
        svgele.appendChild(cirele);
    }

    // draw crosshair on center-of-rotation
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
            // we need to draw the matched stars even though the stars have already been draw
            // this will prevent hot pixels from hiding an important star
            var solstars = obj["solution"]["matches"];
            solstars.forEach(function(ele, idx) {
                var cx = ele["cx"];
                var cy = ele["cy"];
                var cirele = document.createElementNS(svgNS, "circle");
                cirele.setAttribute("cx", Math.round((cx / imgscale) - offset_x));
                cirele.setAttribute("cy", Math.round((cy / imgscale) - offset_y));
                cirele.setAttribute("r", math_mapStarRadius(ele["r"], minr, maxr, imgh));
                cirele.setAttribute("style", "fill:rgb(255,255,128);stroke:none;");
                svgele.appendChild(cirele);
            });

            var sc_x = obj["star_x"];
            var sc_y = obj["star_y"];

            var notinview = (((sc_x / imgscale) - offset_x) < 0 || ((sc_x / imgscale) - offset_x) > imgw || ((sc_y / imgscale) - offset_y) < 0 || ((sc_y / imgscale) - offset_y) > imgh);

            if (hotpixels.length > 0 && notinview == false)
            {
                // just in case hot-pixel filtering removed Polaris
                cirele = document.createElementNS(svgNS, "circle");
                cirele.setAttribute("cx", Math.round((sc_x / imgscale) - offset_x));
                cirele.setAttribute("cy", Math.round((sc_y / imgscale) - offset_y));
                cirele.setAttribute("r", math_mapStarRadius(maxr, minr, maxr, imgh));
                cirele.setAttribute("style", "fill:white;stroke:none;");
                svgele.appendChild(cirele);
            }

            // identify Polaris with a green dot
            cirele = document.createElementNS(svgNS, "circle");
            cirele.setAttribute("cx", Math.round((sc_x / imgscale) - offset_x));
            cirele.setAttribute("cy", Math.round((sc_y / imgscale) - offset_y));
            cirele.setAttribute("r", 5);
            cirele.setAttribute("style", "fill:lime;stroke:none;");
            svgele.appendChild(cirele);

            if (zoom > 1 && notinview)
            {
                // draw a line from the crosshair to Polaris if Polaris is not in view
                var tline = document.createElementNS(svgNS, "line");
                tline.setAttribute("x1", Math.round(cent_x - offset_x));
                tline.setAttribute("x2", Math.round((sc_x / imgscale) - offset_x));
                tline.setAttribute("y1", Math.round(cent_y - offset_y));
                tline.setAttribute("y2", Math.round((sc_y / imgscale) - offset_y));
                tline.setAttribute("style", "stroke:lime;stroke-width:1");
                svgele.appendChild(tline);
            }

            var poly = document.createElementNS(svgNS, "polygon");
            var px = (obj["pole_x"] / imgscale) - offset_x;
            var py = (obj["pole_y"] / imgscale) - offset_y;
            var len = 7, cor = 4;
            if (len < maxr) {
                len = maxr;
            }

            var levelRotation = obj["rotation"] + obj["polar_clock"];

            if ($( "#chkrefraction-1").prop("checked") && refraction != null && refraction != false)
            {
                // if we need to shift the target to compenssate for refraction
                // then we need to account for the camera rotation vs the polar clock
                // with this rotation accounted for, we know which direction to shift the target
                var movedP = math_movePointTowards([px, py], [refraction[0] * obj["pix_per_deg"] / imgscale, levelRotation + 90.0]);
                px = movedP[0];
                py = movedP[1];
            }

            // this draws a cool looking cross hair with a 1-pixel space in the middle for aiming
            var points = (px - 1).toString() + "," + (py - 1).toString() + " ";
            points += (px - 1).toString() + "," + (py - 1 - len).toString() + " ";
            points += (px - cor).toString() + "," + (py - cor).toString() + " ";
            points += (px - 1 - len).toString() + "," + (py - 1).toString() + " ";
            poly.setAttribute("points", points.trim());
            poly.setAttribute("style", "fill:red;stroke:none;");
            svgele.appendChild(poly);
            poly = document.createElementNS(svgNS, "polygon");
            points = (px + 1).toString() + "," + (py - 1).toString() + " ";
            points += (px + 1).toString() + "," + (py - 1 - len).toString() + " ";
            points += (px + cor).toString() + "," + (py - cor).toString() + " ";
            points += (px + 1 + len).toString() + "," + (py - 1).toString() + " ";
            poly.setAttribute("points", points.trim());
            poly.setAttribute("style", "fill:red;stroke:none;");
            svgele.appendChild(poly);
            poly = document.createElementNS(svgNS, "polygon");
            points = (px + 1).toString() + "," + (py + 1).toString() + " ";
            points += (px + 1).toString() + "," + (py + 1 + len).toString() + " ";
            points += (px + cor).toString() + "," + (py + cor).toString() + " ";
            points += (px + 1 + len).toString() + "," + (py + 1).toString() + " ";
            poly.setAttribute("points", points.trim());
            poly.setAttribute("style", "fill:red;stroke:none;");
            svgele.appendChild(poly);
            poly = document.createElementNS(svgNS, "polygon");
            points = (px - 1).toString() + "," + (py + 1).toString() + " ";
            points += (px - 1).toString() + "," + (py + 1 + len).toString() + " ";
            points += (px - cor).toString() + "," + (py + cor).toString() + " ";
            points += (px - 1 - len).toString() + "," + (py + 1).toString() + " ";
            poly.setAttribute("points", points.trim());
            poly.setAttribute("style", "fill:red;stroke:none;");
            svgele.appendChild(poly);

            // if the NCP is out-of-view, draw a line towards it
            if (px < 0 || px > imgw || py < 0 || py > imgh)
            {
                var tline = document.createElementNS(svgNS, "line");
                tline.setAttribute("x1", Math.round(cent_x - offset_x));
                tline.setAttribute("x2", Math.round(px));
                tline.setAttribute("y1", Math.round(cent_y - offset_y));
                tline.setAttribute("y2", Math.round(py));
                tline.setAttribute("style", "stroke:red;stroke-width:1");
                svgele.appendChild(tline);
            }

            if (simpcali_results !== null && simpcali_results !== false)
            {
                if (simpcali_results.cent_x != null && simpcali_results.cent_x != 0 && simpcali_results.cent_y != null && simpcali_results.cent_y != 0)
                {
                    // this draws the intersection lines for the calibration
                    var gline = document.createElementNS(svgNS, "line");
                    gline.setAttribute("x1", Math.round((simpcali_results.cent_x / imgscale) - offset_x));
                    gline.setAttribute("x2", Math.round((simpcali_results.mp1_x  / imgscale) - offset_x));
                    gline.setAttribute("y1", Math.round((simpcali_results.cent_y / imgscale) - offset_y));
                    gline.setAttribute("y2", Math.round((simpcali_results.mp1_y  / imgscale) - offset_y));
                    gline.setAttribute("style", "stroke:deepskyblue;stroke-width:1");
                    svgele.appendChild(gline);
                    gline = document.createElementNS(svgNS, "line");
                    gline.setAttribute("x1", Math.round((simpcali_results.cent_x / imgscale) - offset_x));
                    gline.setAttribute("x2", Math.round((simpcali_results.mp2_x  / imgscale) - offset_x));
                    gline.setAttribute("y1", Math.round((simpcali_results.cent_y / imgscale) - offset_y));
                    gline.setAttribute("y2", Math.round((simpcali_results.mp2_y  / imgscale) - offset_y));
                    gline.setAttribute("style", "stroke:blue;stroke-width:1");
                    svgele.appendChild(gline);
                    gline = document.createElementNS(svgNS, "line");
                    gline.setAttribute("x1", Math.round((simpcali_results.star_x   / imgscale) - offset_x));
                    gline.setAttribute("x2", Math.round((simpcali_results.ghost_sx / imgscale) - offset_x));
                    gline.setAttribute("y1", Math.round((simpcali_results.star_y   / imgscale) - offset_y));
                    gline.setAttribute("y2", Math.round((simpcali_results.ghost_sy / imgscale) - offset_y));
                    gline.setAttribute("style", "stroke:deepskyblue;stroke-width:1");
                    svgele.appendChild(gline);
                    gline = document.createElementNS(svgNS, "line");
                    gline.setAttribute("x1", Math.round((simpcali_results.pole_x   / imgscale) - offset_x));
                    gline.setAttribute("x2", Math.round((simpcali_results.ghost_px / imgscale) - offset_x));
                    gline.setAttribute("y1", Math.round((simpcali_results.pole_y   / imgscale) - offset_y));
                    gline.setAttribute("y2", Math.round((simpcali_results.ghost_py / imgscale) - offset_y));
                    gline.setAttribute("style", "stroke:blue;stroke-width:1");
                    svgele.appendChild(gline);
                }
            }

            var drawLevel = true;
            if (drawLevel)
            {
                draw_level(30, [31, 31], levelRotation, svgele);
            }
        }
    }

    if (ghost != null && ghost != false && advcali_data.length <= 1)
    {
        // this draws the ghost star positions
        var gcir = document.createElementNS(svgNS, "circle");
        gcir.setAttribute("cx", Math.round((ghost.star_x / imgscale) - offset_x));
        gcir.setAttribute("cy", Math.round((ghost.star_y / imgscale) - offset_y));
        gcir.setAttribute("r", 3);
        gcir.setAttribute("style", "stroke:deepskyblue;stroke-width:2");
        svgele.appendChild(gcir);
        gcir = document.createElementNS(svgNS, "rect");
        var cx = Math.round((ghost.pole_x / imgscale) - offset_x);
        var cy = Math.round((ghost.pole_y / imgscale) - offset_y);
        gcir.setAttribute("x", cx - 2);
        gcir.setAttribute("y", cy - 2);
        gcir.setAttribute("width", 4);
        gcir.setAttribute("height", 4);
        gcir.setAttribute("style", "stroke:deepskyblue;stroke-width:2");
        svgele.appendChild(gcir);
    }
    else
    {
        if (advcali_data.length > 0) {
            advcali_data.forEach(function(ele,idx){
                var gcir = document.createElementNS(svgNS, "circle");
                gcir.setAttribute("cx", Math.round((ele.pole[0] / imgscale) - offset_x));
                gcir.setAttribute("cy", Math.round((ele.pole[1] / imgscale) - offset_y));
                gcir.setAttribute("r", 4);
                gcir.setAttribute("style", "fill:none;stroke:deepskyblue;stroke-width:2");
                svgele.appendChild(gcir);
                gcir = document.createElementNS(svgNS, "circle");
                gcir.setAttribute("cx", Math.round((ele.star[0] / imgscale) - offset_x));
                gcir.setAttribute("cy", Math.round((ele.star[1] / imgscale) - offset_y));
                gcir.setAttribute("r", 4);
                gcir.setAttribute("style", "fill:none;stroke:deepskyblue;stroke-width:2");
                svgele.appendChild(gcir);
            });
        }

        if (advcali_tmp1 != null) {
            var gcir = document.createElementNS(svgNS, "circle");
            gcir.setAttribute("cx", Math.round((advcali_tmp1.coord[0] / imgscale) - offset_x));
            gcir.setAttribute("cy", Math.round((advcali_tmp1.coord[1] / imgscale) - offset_y));
            gcir.setAttribute("r", Math.round(advcali_tmp1.avg / imgscale));
            gcir.setAttribute("style", "fill:none;stroke:deepskyblue;stroke-width:1");
            svgele.appendChild(gcir);
        }

        if (advcali_tmp2 != null) {
            var gcir = document.createElementNS(svgNS, "circle");
            gcir.setAttribute("cx", Math.round((advcali_tmp2.coord[0] / imgscale) - offset_x));
            gcir.setAttribute("cy", Math.round((advcali_tmp2.coord[1] / imgscale) - offset_y));
            gcir.setAttribute("r", Math.round(advcali_tmp2.avg / imgscale));
            gcir.setAttribute("style", "fill:none;stroke:deepskyblue;stroke-width:1");
            svgele.appendChild(gcir);
        }
    }

    imgdiv.appendChild(svgele);
}

function draw_level(rad, pos, rot, svgele)
{
    var pp;

    var cirele = document.createElementNS(svgNS, "path");
    var pp1 = math_movePointTowards(pos, [rad, rot]);
    var pp2 = math_movePointTowards(pos, [rad, rot + 180]);
    var pathstr = "M" + pp1[0] +  "," + pp1[1] + " " + "A" + rad + "," + rad + " " + rot + " 0 1 " + pp2[0] +  "," + pp2[1];
    cirele.setAttribute("d", pathstr);
    cirele.setAttribute("style", "fill:saddlebrown;stroke:none;");
    svgele.appendChild(cirele);
    cirele = document.createElementNS(svgNS, "path");
    pathstr = "M" + pp1[0] +  "," + pp1[1] + " " + "A" + rad + "," + rad + " " + rot + " 0 0 " + pp2[0] +  "," + pp2[1];
    cirele.setAttribute("d", pathstr);
    cirele.setAttribute("style", "fill:darkblue;stroke:none;");
    svgele.appendChild(cirele);
    cirele = document.createElementNS(svgNS, "circle");
    cirele.setAttribute("cx", rad + 1);
    cirele.setAttribute("cy", rad + 1);
    cirele.setAttribute("r", rad);
    cirele.setAttribute("style", "fill:none;stroke:lime;stroke-width:1");
    svgele.appendChild(cirele);
    cline = document.createElementNS(svgNS, "line");
    pp = math_movePointTowards([rad + 1, rad + 1], [rad - 2, rot]);
    cline.setAttribute("x1", pp[0]);
    cline.setAttribute("y1", pp[1]);
    pp = math_movePointTowards([rad + 1, rad + 1], [rad - 2, rot + 180]);
    cline.setAttribute("x2", pp[0]);
    cline.setAttribute("y2", pp[1]);
    cline.setAttribute("style", "stroke:lime;stroke-width:1");
    svgele.appendChild(cline);
    pp = math_movePointTowards([rad + 1, rad + 1], [21.21, rot + 45])
    cline = document.createElementNS(svgNS, "line");
    cline.setAttribute("x1", pp[0]);
    cline.setAttribute("y1", pp[1]);
    pp = math_movePointTowards([rad + 1, rad + 1], [21.21, rot + (180 - 45)]);
    cline.setAttribute("x2", pp[0]);
    cline.setAttribute("y2", pp[1]);
    cline.setAttribute("style", "stroke:green;stroke-width:1");
    svgele.appendChild(cline);
    pp = math_movePointTowards([rad + 1, rad + 1], [16.77, rot - 63.43])
    cline = document.createElementNS(svgNS, "line");
    cline.setAttribute("x1", pp[0]);
    cline.setAttribute("y1", pp[1]);
    pp = math_movePointTowards([rad + 1, rad + 1], [16.77, rot - (180 - 63.43)]);
    cline.setAttribute("x2", pp[0]);
    cline.setAttribute("y2", pp[1]);
    cline.setAttribute("style", "stroke:blue;stroke-width:1");
    svgele.appendChild(cline);
}
